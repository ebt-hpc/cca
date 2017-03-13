#!/usr/bin/env python
#-*- coding: utf-8 -*-

'''
  A script for topic analysis of documents

  Copyright 2013-2017 RIKEN

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
'''

__author__ = 'Masatomo Hashimoto <m.hashimoto@riken.jp>'

import os.path
from itertools import chain
import cPickle
import json
import re

import pathsetup
import dp
from gensim import models, corpora, similarities
from analyze_topic import get_texts, lsi, lda, rp

FNAME_PAT_FORTRAN = r'(.*readme.*)|(.+\.(f|f90|f95|ftn|for|f03|f08))'

FNAME_PAT_TBL = {
    'fortran' : FNAME_PAT_FORTRAN,
}

MODEL_LOADER_TBL = {
    'lda' : models.LdaModel.load,
    'lsi' : models.LsiModel.load,
    'rp'  : models.RpModel.load,
}

def ensure_dir(d):
    b = True
    if not os.path.exists(d):
        try:
            os.makedirs(d)
        except Exception, e:
            dp.warning(str(e))
            b = False
    return b


def search(index_path, mname, dpath, ntopics=32, nsims=10, lang='fortran', outfile=None):
    try:
        ldmodel = MODEL_LOADER_TBL[mname]
    except KeyError:
        dp.error('model not found: %s' % mname)

    (a, _) = os.path.splitext(index_path)

    dp.message('loading dictionary...')

    dictionary = corpora.Dictionary.load(a+'.dict')

    dp.message('loading model...')
    model = ldmodel(a+'.model')

    texts = get_texts(dpath, FNAME_PAT_TBL[lang])

    text = list(chain.from_iterable(texts))

    dp.message('loading index...')

    index = similarities.MatrixSimilarity.load(index_path)

    bow = dictionary.doc2bow(text)

    tfidf_path = os.path.join(os.path.dirname(index_path), 'survey.tfidf')

    tfidf = models.TfidfModel.load(tfidf_path)
    vec_tfidf = tfidf[bow]

    print('*** TF-IDF:')
    print(', '.join(['%s:%f' % (dictionary[i], v) for (i, v) in sorted(vec_tfidf, key=lambda x: -x[1])[0:32]]))
    
    vec = model[bow]

    sims = sorted(enumerate(index[vec]), key=lambda x: -x[1])

    classes = cPickle.load(open(a+'.classes', 'rb'))

    if outfile:
        if ensure_dir(os.path.dirname(outfile)):
            with open(outfile, 'w') as f:
                data = []
                for sim in sims[0:nsims]:
                    data.append({'topic':classes[sim[0]], 'similarity':str(sim[1])})
                json.dump(data, f)

    print('*** Similarities:')
    for sim in sims[0:nsims]:
        print('%s: %f' % (classes[sim[0]], sim[1]))

    

if __name__ == '__main__':
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

    parser = ArgumentParser(description='analyze topics of documents',
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                        help='enable debug printing')

    parser.add_argument('-m', '--model', dest='model', metavar='MODEL', type=str,
                        default='lsi', help='model (lda|lsi|rp)')

    parser.add_argument('-t', '--ntopics', dest='ntopics', metavar='N', type=int,
                        default=32, help='number of topics')

    parser.add_argument('-n', '--nsims', dest='nsims', metavar='N', type=int,
                        default=5, help='number of topic-similarity pairs')

    parser.add_argument('-o', '--outfile', dest='outfile', default=None,
                        metavar='FILE', type=str, help='dump JSON into FILE')

    parser.add_argument('index_path', metavar='INDEX_FILE', type=str, help='index file')

    parser.add_argument('dpath', metavar='PATH', type=str, help='directory')

    args = parser.parse_args()

    dp.debug_flag = args.debug
    
    search(args.index_path, args.model, args.dpath, 
           ntopics=args.ntopics, nsims=args.nsims, outfile=args.outfile)
