import json
import logging
from StringIO import StringIO
from urllib import urlencode

from werkzeug.exceptions import BadRequest
from flask import Blueprint, render_template, request, redirect
from flask import Response
from flask.ext.login import current_user

from openspending.core import db
from openspending.model import Tags

log = logging.getLogger(__name__)


blueprint = Blueprint('viz', __name__)





@blueprint.route('/visualization')
#@blueprint.route('/datasets.<fmt:format>')
def visualization(format='html'):
    """ Get the datasets indicators list by sec"""
    # tags = []
    # for tag in Tags.all_by_category().all():
    #     tags.append(tag.as_dict())

    return render_template('visualization/visualization.jade')


@blueprint.route('/data-visualization')
#@blueprint.route('/datasets.<fmt:format>')
def datavisualization(format='html'):
    """ Get the datasets indicators list by sec"""
    # tags = []
    # for tag in Tags.all_by_category().all():
    #     tags.append(tag.as_dict())

    return render_template('dataviz/data-visualization.jade')


@blueprint.route('/countries')
#@blueprint.route('/datasets.<fmt:format>')
def countries(format='html'):
    """ Get the datasets indicators list by category"""
    # tags = []
    # for tag in Tags.all_by_category().all():
    #     tags.append(tag.as_dict())

    return render_template('countries/countries.jade')

@blueprint.route('/sectors')
#@blueprint.route('/datasets.<fmt:format>')
def sectors(format='html'):
    """ Get the datasets indicators list by category"""
    # tags = []
    # for tag in Tags.all_by_category().all():
    #     tags.append(tag.as_dict())

    return render_template('sectors/sectors.jade')

@blueprint.route('/data')
#@blueprint.route('/datasets.<fmt:format>')
def data(format='html'):
    """ Get the datasets indicators list by category"""
    # tags = []
    # for tag in Tags.all_by_category().all():
    #     tags.append(tag.as_dict())

    return render_template('data/data.jade')