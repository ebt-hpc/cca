#!/usr/bin/env python3


'''
  A script for loop classification

  Copyright 2013-2018 RIKEN
  Copyright 2018-2020 Chiba Institute of Technology

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

__author__ = 'Masatomo Hashimoto <m.hashimoto@stair.center>'

import os
import csv
import numpy as np

from sklearn import preprocessing as pp
import joblib

import pathsetup
import dp
from make_loop_classifier import META, METRICS, fromstring, get_derived, Data
from make_loop_classifier import SELECTED_MINAMI, DERIVED_MINAMI
from make_loop_classifier import SELECTED_TERAI, DERIVED_TERAI
from make_loop_classifier import SELECTED_MIX, DERIVED_MIX


def import_test_set(path, selected=SELECTED_MINAMI, derived=DERIVED_MINAMI, filt={}):
    _X = []
    meta = []
    try:
        with open(path, newline='') as f:
            reader = csv.DictReader(f)

            count = 0

            for row in reader:

                d = dict((k, fromstring(row[k])) for k in METRICS)

                skip = False

                for k0, f in filt.items():
                    v0 = d[k0]
                    b0 = f(v0)
                    dp.debug('k0=%s d[k0]=%s f(d[k0])=%s sub=%s' % (k0, v0, b0, row['sub']))
                    if not b0:
                        skip = True

                x = [d[k] for k in selected]

                for k in derived:
                    v = get_derived(k, d)

                    try:
                        f = filt[k]
                        if not f(v):
                            skip = True
                    except:
                        pass

                    x.append(v)

                dp.debug('skip=%s' % skip)
                if skip:
                    continue

                m = dict((k, row[k]) for k in META)

                _X.append(x)
                meta.append(m)

                count += 1

            dp.message('%d rows' % count)

    except Exception as e:
        dp.warning(str(e))

    X = np.array(_X)

    data = Data(X, None, meta)

    return data

def classify(path, clf_path, model='minami', filt={}, verbose=True):

    clf = joblib.load(clf_path)

    selected = SELECTED_MINAMI
    derived = DERIVED_MINAMI

    if model == 'minami':
        selected = SELECTED_MINAMI
        derived = DERIVED_MINAMI

    elif model == 'terai':
        selected = SELECTED_TERAI
        derived = DERIVED_TERAI

    elif model == 'mix':
        selected = SELECTED_MIX
        derived = DERIVED_MIX
        
    else:
        dp.warning('"%s" is not supported. using default model' % model)

    data = import_test_set(path, selected=selected, derived=derived, filt=filt)

    data_pred = None

    if len(data.X) > 0:

        X = pp.scale(data.X)

        y_pred = clf.predict(X)

        data_pred = Data(X, y_pred, data.meta)

        if verbose:
            for i in range(len(y_pred)):
                m = data.meta[i]
                m['pred'] = y_pred[i]
                print('[%(proj)s][%(ver)s][%(path)s:%(lnum)s][%(sub)s] --> %(pred)s' % m)

    return data_pred

if __name__ == '__main__':
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

    parser = ArgumentParser(description='classify loops',
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                        help='enable debug printing')

    parser.add_argument('-m', '--model', dest='model', metavar='MODEL', type=str,
                        default='minami', help='model (minami|terai|mix)')

    parser.add_argument('clf', metavar='CLF_PATH', 
                        type=str, default='a.pkl', help='dumped classifier')

    parser.add_argument('dpath', metavar='DATA_PATH', type=str, help='test dataset')

    args = parser.parse_args()

    dp.debug_flag = args.debug

    classify(args.dpath, args.clf, model=args.model)
