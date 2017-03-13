#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
  Counting operations in Fortran programs

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

import os
import re
from urllib import urlencode
import json

import pathsetup
import dp
import project
from siteconf import PROJECTS_DIR
import Git2
from outline_for_survey import gen_conf, gen_conf_a, GIT_REPO_BASE, ensure_dir, get_proj_list



README_LINKS_DIR_NAME = 'readme_links'

README_PAT = re.compile(r'.*readme.*', re.I)


class Collector(dp.base):
    def __init__(self, proj_id, gitrepo=GIT_REPO_BASE):
        self._proj_id = proj_id

        self._gitrepo = gitrepo

        self._conf = project.get_conf(proj_id)
        if not self._conf:
            if proj_id.endswith('_git'):
                self._conf = gen_conf(proj_id)
            else:
                self._conf = gen_conf_a(proj_id, '')


    def from_dir(self):
        projs_path = os.path.abspath(PROJECTS_DIR)
        projs_loc = os.path.dirname(projs_path)
        proj_dir = os.path.join(projs_path, self._proj_id)
        l = []
        for (dpath, dns, fns) in os.walk(proj_dir):
            for fn in fns:
                m = README_PAT.match(fn)
                if m:
                    p = os.path.join(dpath, fn)
                    rpath = re.sub(r'^%s' % proj_dir, '', p).lstrip(os.sep)
                    path = re.sub(r'^%s' % projs_loc, '', p).lstrip(os.sep)
                    url = 'getsrc?%s' % urlencode({'path':path})
                    l.append({'url':url,'path':rpath})

        return l



    def from_git(self):
        repo_name = self._conf.gitweb_proj_id
        repo_path = os.path.normpath(os.path.join(self._gitrepo, repo_name))
        repo = Git2.Repository(repo_path)

        def filt(fn):
            m = README_PAT.match(fn)
            b = False
            if m:
                b = True
            return b

        l = []

        for d in repo.find_files('HEAD', filt):
            path = d['path']
            url = '/gitweb/?p=%(name)s;a=blob_plain;f=%(path)s' % {'name':repo_name,
                                                                   'path':path,
            }
            l.append({'url':url,'path':path})

        return l


    def collect(self):
        links = []
        if self._conf.is_vkind_gitrev():
            links = self.from_git()
        else:
            links = self.from_dir()

        return links
        

def collect_readme(proj, outdir, gitrepo=GIT_REPO_BASE):
    c = Collector(proj, gitrepo=gitrepo)

    links = c.collect()

    json_dir = os.path.join(outdir, README_LINKS_DIR_NAME)
    if ensure_dir(json_dir):
        json_path = os.path.join(json_dir, proj+'.json')
        try:
            with open(json_path, 'w') as jsonf:
                json.dump(links, jsonf)

        except Exception, e:
            dp.warning(str(e))

    for d in links:
        print('* %(path)s: %(url)s' % d)

    print('%d readmes found' % len(links))



def main():
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

    parser = ArgumentParser(description='analyze topics of documents')

    parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                        help='enable debug printing')

    parser.add_argument('-g', '--git-repo-base', dest='gitrepo', metavar='DIR', type=str,
                        default=GIT_REPO_BASE, help='location of git repositories')

    parser.add_argument('-o', '--outdir', dest='outdir', default='.',
                        metavar='DIR', type=str, help='dump data into DIR')


    parser.add_argument('proj_list', nargs='*', default=[], 
                        metavar='PROJ', type=str,
                        help='project id (default: all projects)')


    args = parser.parse_args()

    dp.debug_flag = args.debug

    proj_list = []

    if args.proj_list:
        proj_list = args.proj_list
    else:
        proj_list = get_proj_list()

    for proj in proj_list:
        collect_readme(proj, args.outdir, gitrepo=args.gitrepo)


if __name__ == '__main__':
    main()
