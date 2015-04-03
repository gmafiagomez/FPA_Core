# -*- coding: utf-8 -*-
from flask import Blueprint, Flask, Response, request, g, current_app
from functools import wraps

from cubes.workspace import Workspace
from cubes.auth import NotAuthorized
from cubes.browser import Cell, cuts_from_string, SPLIT_DIMENSION_NAME
from cubes.errors import *
from cubes.server.utils import *
from cubes.server.errors import *
from cubes.server.local import *
from cubes.server.decorators import prepare_cell
from cubes.calendar import CalendarMemberConverter
from cubes.model import Cube, create_dimension

from contextlib import contextmanager



def requires_complex_browser(f):
    """Prepares three global variables: `g.cube`, `g.browser` and `g.cell`.
    Also athorizes the cube using `authorize()`."""

    @wraps(f)
    def wrapper(*args, **kwargs):

        star_name = request.view_args.get("star_name")
        g.star_name = star_name


        if "lang" in request.args:
            g.locale = request.args.get("lang")
        else:
            g.locale = None


        #prepare_cell(restrict=False)


        if "page" in request.args:
            try:
                g.page = int(request.args.get("page"))
            except ValueError:
                raise RequestError("'page' should be a number")
        else:
            g.page = None

        if "pagesize" in request.args:
            try:
                g.page_size = int(request.args.get("pagesize"))
            except ValueError:
                raise RequestError("'pagesize' should be a number")
        else:
            g.page_size = None

        # Collect orderings:
        # order is specified as order=<field>[:<direction>]
        #
        g.order = []
        for orders in request.args.getlist("order"):
            for order in orders.split(","):
                split = order.split(":")
                if len(split) == 1:
                    g.order.append( (order, None) )
                else:
                    g.order.append( (split[0], split[1]) )

        return f(*args, **kwargs)

    return wrapper

def get_complex_cube(star_name, cubes):

    #skipping authorization without "authorized_cube" func
    #the workspace.cube function will raiseerror if cube is not found
    star_cube_raw = current_app.cubes_workspace.cube(star_name, locale=g.locale, metaonly=True)
    star_cube = add_table_identifier(star_cube_raw, seperator="__")


    cubes_meta = []
    for cube_name in cubes:
        if cube_name:
            cube_joiner_meta_raw = current_app.cubes_workspace.cube(cube_name, locale=g.locale, metaonly=True)
            cube_joiner_meta = add_table_identifier(cube_joiner_meta_raw, seperator="__")
            cubes_meta.append(cube_joiner_meta)
    
    star_cube = coalesce_cubes(star_cube, cubes_meta)

    print "here is star cube", star_cube


    return Cube(name=star_cube['name'],
                            fact=star_cube['fact'],
                            aggregates=star_cube['aggregates'],
                            measures=star_cube['measures'],
                            label=star_cube['label'],
                            description=star_cube['description'],
                            dimensions=star_cube['dimensions'],
                            store=star_cube['store'],
                            mappings=star_cube['mappings'],
                            joins=star_cube['joins'])


def figure_out_deps(masterjoin, rightjointable):
    #makes sure all the deps are in the right order
    finaljoins = []
    tempmaster = []
    for t in range(len(masterjoin)):
        if masterjoin[t]['detail'].split('.')[0] == rightjointable:
            finaljoins.append({'master':masterjoin[t]['detail'], 'detail':masterjoin[t]['master']})
        else:
            tempmaster.append(masterjoin[t])

    #repeat until all tempmasters are popped
    while (len(tempmaster) >0):
        mypops = []
        #look at all of the tempmasters available
        for j in range(len(tempmaster)):
            #if finaljoins doesn't have anything in it then check tempmaster for those that don't have deailts
            no_master = True
            for z in range(len(tempmaster)):
                if tempmaster[z]['detail'].split('.')[0] == tempmaster[j]['master'].split('.')[0]:
                    no_master = False
            if no_master:
                mypops.append(j)
        newlist = []
        for p in range(len(tempmaster)):
            if p in mypops:
                finaljoins.append(tempmaster[p])
            else:
                newlist.append(tempmaster[p])
        tempmaster = newlist



    return finaljoins



def sort_on_deps(joinslist, detail_table):

    #find the instance of this detail table in master and move it to the top

    theindex = -1
    for j in range(len(joinslist)):
        if joinslist[j]['detail'].split(".")[0] == detail_table:
            theindex = j
            continue
    keyjoin = {'master': joinslist[theindex]['detail'], 'detail':joinslist[theindex]['master']}
    joinslist.pop(theindex)
    joinslist.insert(0, keyjoin)
    return joinslist

def add_table_identifier(meta_data, seperator="__"):
    for item in ['aggregates', 'measures', 'dimensions']:
        for dim in meta_data[item]:
            dim.name = meta_data['name'] + seperator + dim.name
            try:
                dim.ref = meta_data['name'] + seperator + dim.ref
            except:
                pass
            try:
                dim.measure = meta_data['name'] + seperator + dim.measure
            except:
                pass
    master_meta_new = {}
    for mapkey in meta_data['mappings']:
       master_meta_new[meta_data['name'] + "__" + mapkey] = meta_data['mappings'][mapkey]
    meta_data['mappings'] = master_meta_new

    meta_data['mappings'][meta_data['name'] + '__amount'] = meta_data['name'] + '__entry.amount'
    meta_data['mappings'].update(meta_data['mappings'])


    return meta_data


#drill down example using hierarchies little documentation in cubes!
#http://localhost:5000/api/slicer/cube/test_geom/aggregate?aggregates=test_geom__amount&drilldown=test_geom__time@monthly:month&cut=test_geom__time.year:2010

def coalesce_cubes(master_meta, cubes_metadata):
    #join on lowest geographical hierarchy across all loaded finge cubes
    #join on year field


    #search for "Country_level0" or country_level0 or any other labels we might apply in case not consistent in data loading
    #before we do amny edits to the master_meta
    candidates = ["country_level0.gid", "country_level0.countryid"]
    leftjoin_field = None
    for joinfield in master_meta['dimensions']:
        if joinfield.name.split('__')[1] + ".gid" in candidates:
            print "FOUND ONE!!!!!!!!!!!!"
            leftjoin_field = joinfield.name+ ".gid" 
            break

    for cube_meta in cubes_metadata:
        rightjoin_field = None
        for joinfield2 in cube_meta['dimensions']:
            print "this hsould have countryid in it", joinfield2
            if joinfield2.name.split('__')[1] + ".countryid" in candidates:
                rightjoin_field = joinfield2.name+ ".countryid" 
                break

        if not rightjoin_field:
            raise RequestError("Could not find join value for '%s'and '%s'.  Checked %s"
                    % (master_meta['name'], cube_meta['name'], candidates) )


        #add in all of the components to the master_meta
        for item in ['aggregates', 'measures', 'dimensions']:
            master_meta[item] = master_meta[item] + cube_meta[item]

        master_meta['mappings'].update(cube_meta['mappings'])


        #join_dict example {"master": "test_geom__Country_level0.label", "detail":"geometry__country_level0.label"}
        master_meta['joins']  = master_meta['joins'] + \
            [{"master": leftjoin_field, "detail":rightjoin_field}] + \
            figure_out_deps(cube_meta['joins'], rightjoin_field.split(".")[0])



    #master_meta['joins'] = figure_out_deps(master_meta['joins'])
    master_meta['joins'] = master_meta['joins'][::-1]


    return master_meta




def getGeomCube(provider, metaonly):


    basemeta = {
                  "name": "geometry",
                  "info": {},
                  "label": "Base Geometry",
                  'fact_table': "geometry__country_level0",
                  "description": "The Base Geometry Table",
                  "aggregates": [],
                  "measures": [],
                  "details": []
                }

    dim_metas = [
                    {
                      "name": "country_level0",
                      "info": {},
                      "label": "Country Name (lower case)",
                      "default_hierarchy_name": "name",
                      "levels": [
                        {
                          "name": "name",
                          "info": {},
                          "label": "Country Name",
                          "key": "name",
                          "label_attribute": "name",
                          "order_attribute": "name",
                          "attributes": [
                            {
                              "name": "name",
                              "info": {},
                              "label": "Country Name",
                              "ref": "geometry__country_level0.name",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "dos_level1",
                          "info": {},
                          "label": "Department of State Country Groupings",
                          "key": "dos_level1",
                          "label_attribute": "dos_level1",
                          "order_attribute": "dos_level1",
                          "attributes": [
                            {
                              "name": "dos_level1",
                              "info": {},
                              "label": "Department of State Country Groupings",
                              "ref": "geometry__country_level0.dos_level1",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "dod_level1",
                          "info": {},
                          "label": "Department of Defense Country Groupings",
                          "key": "dod_level1",
                          "label_attribute": "dod_level1",
                          "order_attribute": "dod_level1",
                          "attributes": [
                            {
                              "name": "dod_level1",
                              "info": {},
                              "label": "Department of Defense Country Groupings",
                              "ref": "geometry__country_level0.dod_level1",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "usaid_level1",
                          "info": {},
                          "label": "USAID Country Groupings",
                          "key": "usaid_level1",
                          "label_attribute": "usaid_level1",
                          "order_attribute": "usaid_level1",
                          "attributes": [
                            {
                              "name": "usaid_level1",
                              "info": {},
                              "label": "USAID Country Groupings",
                              "ref": "geometry__country_level0.usaid_level1",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "bureau",
                          "info": {},
                          "label": "Bureau Country Groupings",
                          "key": "bureau",
                          "label_attribute": "bureau",
                          "order_attribute": "bureau",
                          "attributes": [
                            {
                              "name": "bureau",
                              "info": {},
                              "label": "Bureau Country Groupings",
                              "ref": "geometry__country_level0.bureau",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "region_wb",
                          "info": {},
                          "label": "World Bank Regions",
                          "key": "region_wb",
                          "label_attribute": "region_wb",
                          "order_attribute": "region_wb",
                          "attributes": [
                            {
                              "name": "region_wb",
                              "info": {},
                              "label": "World Bank Regions",
                              "ref": "geometry__country_level0.region_wb",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "subregion",
                          "info": {},
                          "label": "Subregion",
                          "key": "subregion",
                          "label_attribute": "subregion",
                          "order_attribute": "subregion",
                          "attributes": [
                            {
                              "name": "subregion",
                              "info": {},
                              "label": "Subregion",
                              "ref": "geometry__country_level0.subregion",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "region_un",
                          "info": {},
                          "label": "UN Regions",
                          "key": "region_un",
                          "label_attribute": "region_un",
                          "order_attribute": "region_un",
                          "attributes": [
                            {
                              "name": "region_un",
                              "info": {},
                              "label": "UN Regions",
                              "ref": "geometry__country_level0.region_un",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "continent",
                          "info": {},
                          "label": "Continent",
                          "key": "continent",
                          "label_attribute": "continent",
                          "order_attribute": "continent",
                          "attributes": [
                            {
                              "name": "continent",
                              "info": {},
                              "label": "Continent",
                              "ref": "geometry__country_level0.continent",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "incomegroup_level1",
                          "info": {},
                          "label": "Income Groups",
                          "key": "incomegroup_level1",
                          "label_attribute": "incomegroup_level1",
                          "order_attribute": "incomegroup_level1",
                          "attributes": [
                            {
                              "name": "incomegroup_level1",
                              "info": {},
                              "label": "Income Groups",
                              "ref": "geometry__country_level0.incomegroup_level1",
                              "locales": []
                            }
                          ]
                        },
                        {
                          "name": "sovereignt",
                          "info": {},
                          "label": "Sovereignty",
                          "key": "sovereignt",
                          "label_attribute": "sovereignt",
                          "order_attribute": "sovereignt",
                          "attributes": [
                            {
                              "name": "sovereignt",
                              "info": {},
                              "label": "Sovereignty",
                              "ref": "geometry__country_level0.sovereignt",
                              "locales": []
                            }
                          ]
                        }
                      ],
                      "hierarchies": [
                        {
                          "name": "name",
                          "info": {},
                          "label": "Country Name",
                          "levels": [
                            "name"
                          ]
                        },                        
                        {
                          "name": "sovereignt",
                          "info": {},
                          "label": "Sovereignty",
                          "levels": [
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "dos_level1",
                          "info": {},
                          "label": "Department of State Regions",
                          "levels": [
                            "dos_level1",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "dod_level1",
                          "info": {},
                          "label": "Department of Defense Regions",
                          "levels": [
                            "dod_level1",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "usaid_level1",
                          "info": {},
                          "label": "USAID Regions",
                          "levels": [
                            "usaid_level1",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "bureau",
                          "info": {},
                          "label": "Bureau Regions",
                          "levels": [
                            "bureau",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "region_wb",
                          "info": {},
                          "label": "World Bank Regions",
                          "levels": [
                            "region_wb",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "subregion",
                          "info": {},
                          "label": "Subregion",
                          "levels": [
                            "subregion",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "region_un",
                          "info": {},
                          "label": "UN Regions",
                          "levels": [
                            "region_un",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "continent",
                          "info": {},
                          "label": "Continents",
                          "levels": [
                            "continent",
                            "sovereignt",
                            "name"
                          ]
                        },
                        {
                          "name": "incomegroup_level1",
                          "info": {},
                          "label": "Income Grouping",
                          "levels": [
                            "incomegroup_level1",
                            "sovereignt",
                            "name"
                          ]
                        }
                      ],
                      "is_flat": False,
                      "has_details": False
                    }
                  ]



    #joins = [{"master": u"geometry__entry.country_level0_id", "detail": u"geometry__country_level0.id"}] 
    joins = []
    mappings = {
                u"country_level0.dos_level1": u"geometry__country_level0.dos_level1", 
                u"country_level0.dod_level1": u"geometry__country_level0.dod_level1",
                u"country_level0.incomegroup_level1": u"geometry__country_level0.incomegroup_level1", 
                u"country_level0.usaid_level1": u"geometry__country_level0.usaid_level1",
                u"country_level0.bureau": u"geometry__country_level0.bureau", 
                u"country_level0.region_wb": u"geometry__country_level0.region_wb", 
                u"country_level0.subregion": u"geometry__country_level0.subregion", 
                u"country_level0.region_un": u"geometry__country_level0.region_un", 
                u"country_level0.continent": u"geometry__country_level0.continent", 
                u"country_level0.sovereignt": u"geometry__country_level0.sovereignt", 
                u"country_level0.id": u"geometry__country_level0.id",
                u"country_level0.name": u"geometry__country_level0.name",
                u"country_level0.label": u"geometry__country_level0.label"
            } 

    dimensions = []
    for dim in dim_metas:
        dimensions.append(create_dimension(dim))



    cube_meta = {"name":basemeta['name'],
                            "fact":basemeta['fact_table'],
                            "aggregates":basemeta['aggregates'],
                            "measures":basemeta['measures'],
                            "label":basemeta['label'],
                            "description":basemeta['description'],
                            "dimensions":dimensions,
                            "store":provider.store,
                            "mappings":mappings,
                            "joins":joins}

    if metaonly:
        return cube_meta
    else:
        return Cube(name=cube_meta['name'],
                        fact=cube_meta['fact'],
                        aggregates=cube_meta['aggregates'],
                        measures=cube_meta['measures'],
                        label=cube_meta['label'],
                        description=cube_meta['description'],
                        dimensions=cube_meta['dimensions'],
                        store=cube_meta['store'],
                        mappings=cube_meta['mappings'],
                        joins=cube_meta['joins'])



