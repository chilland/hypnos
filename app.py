import os
import json
import requests
from tornado.ioloop import IOLoop
from tornado.wsgi import WSGIContainer
from tornado.httpserver import HTTPServer
from flask import Flask, jsonify, make_response
from flask.ext.restful import Api, Resource, reqparse

app = Flask(__name__)
api = Api(app)

cwd = os.path.abspath(os.path.dirname(__file__))


@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': 'Bad request'}), 400)


@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)


class ExtractAPI(Resource):
    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument('text', type=unicode, location='json')
        self.reqparse.add_argument('id', type=unicode, location='json')
        self.reqparse.add_argument('date', type=unicode, location='json')
        super(ExtractAPI, self).__init__()

    def get(self):
        args = self.reqparse.parse_args()
        text = args['text']
        text = text.encode('utf-8')
        storyid = args['id']
        date = args['date']

        headers = {'Content-Type': 'application/json'}
        ccnlp = os.environ.get('CORENLP_DOCKER_PORT_9000_TCP_ADDR')
        ccnlp_url = 'http://{}:9000/?properties='.format(ccnlp)
        properties = {'annotators': 'parse', 
                      'outputFormat': 'json', 
                      'tokenize.whitespace': 'true'}
        r = requests.post(ccnlp_url, json=text, params=properties, headers=headers)
        out = r.json()

        event_dict = process_corenlp(out, date, storyid)

        events_data = json.dumps({'events': event_dict})
        petr = os.environ.get('PETRARCH_PORT_5001_TCP_ADDR')
        petr_url = 'http://{}:5001/petrarch/code'.format(petr)
        events_r = requests.post(petr_url, data=events_data, headers=headers)
        event_updated = process_results(events_r.json())

        return event_updated


def process_corenlp(output, date, STORYID):
    event_dict = {STORYID: {}}
    event_dict[STORYID]['sents'] = {}
    event_dict[STORYID]['meta'] = {}
    event_dict[STORYID]['meta']['date'] = date
    for i, sent in enumerate(output['sentences']):
        sents = output['sentences']
        event_dict[STORYID]['sents'][i] = {}
        tokens = [j['word'] for j in sents[i]['tokens']]
        event_dict[STORYID]['sents'][i]['content'] = ' '.join(tokens)
        paren_space = sents[i]['parse'].upper().replace(')', ' )')
        event_dict[STORYID]['sents'][i]['parsed'] =paren_space.replace('\n','')
    return event_dict


def process_results(event_dict):
    for s_id in event_dict:
        sents = event_dict[s_id]['sents']
        for sent in sents:
            if 'issues' not in sents[sent].keys():
                sents[sent]['issues'] = []
            if 'events' not in sents[sent].keys():
                sents[sent]['events'] = []

    return event_dict

api.add_resource(ExtractAPI, '/hypnos/extract')

if __name__ == '__main__':
    http_server = HTTPServer(WSGIContainer(app))
    http_server.listen(5002)
    IOLoop.instance().start()
