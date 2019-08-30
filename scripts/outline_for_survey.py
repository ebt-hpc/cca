#!/usr/bin/env python
#-*- coding: utf-8 -*-

'''
  A script for outlining Fortran programs

  Copyright 2013-2018 RIKEN
  Copyright 2017-2019 Chiba Institute of Technology

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
import sys
import json
from urllib import pathname2url, urlencode, urlopen
import re
import csv
import codecs
from time import time
import msgpack

import pathsetup
import dp
from cca_config import PROJECTS_DIR, Config, VKIND_VARIANT, VKIND_GITREV
import project

from sparql import get_localname
import sparql
from factutils.entity import SourceCodeEntity
from ns import FB_NS, NS_TBL
from sourcecode_metrics_for_survey import get_proj_list, get_lver, Metrics
import sourcecode_metrics_for_survey as metrics
from search_topic_for_survey import search
from siteconf import GIT_REPO_BASE
import Git2
from virtuoso import VIRTUOSO_PW, VIRTUOSO_PORT

###

MARKER_CALLEE_PAT = re.compile('^.*(dgemm|timer|start|begin).*$')

OMITTED = ['execution-part','do-block']

QN_SEP = ','

NID_SEP = '_'

LEADING_DIGITS_PAT = re.compile(r'^\d+')

def remove_leading_digits(s):
    r = LEADING_DIGITS_PAT.sub('', s)
    return r

SUBPROGS = set([
    'subroutine-external-subprogram',
    'subroutine-internal-subprogram',
    'subroutine-module-subprogram',
    'function-external-subprogram',
    'function-internal-subprogram',
    'function-module-subprogram',
])

LOOPS = set(['do-construct','do-stmt','end-do-stmt','do-block'])

CALLS = set(['call-stmt','function-reference','part-name'])

GITREV_PREFIX = NS_TBL['gitrev_ns']

OUTLINE_DIR = 'outline'
OUTLINE_FILE_FMT = '%s.msg'

TOPIC_DIR = 'topic'
TOPIC_FILE_FMT = '%s.json'

METRICS_DIR = 'metrics'
METRICS_FILE_FMT = '%s.csv'
METRICS_ROW_HEADER = list(metrics.abbrv_tbl.keys()) + metrics.META_KEYS + ['nid','root_file']

TYPE_TBL = { # cat -> type
    'file'                           : 'file',

    'do-construct'                   : 'loop',
    'if-construct'                   : 'branch',
    'case-construct'                 : 'branch',
    'select-type-construct'          : 'branch',
    'where-construct'                : 'branch',

    'call-stmt'                      : 'call',
    'function-reference'             : 'call',
    'part-name'                      : 'call',

    'main-program'                   : 'main',
    'subroutine-external-subprogram' : 'subroutine',
    'subroutine-internal-subprogram' : 'subroutine',
    'subroutine-module-subprogram'   : 'subroutine',
    'function-external-subprogram'   : 'function',
    'function-internal-subprogram'   : 'function',
    'function-module-subprogram'     : 'function',

    'execution-part'                 : 'part',

    'if-then-block'                  : 'block',
    'else-if-block'                  : 'block',
    'else-block'                     : 'block',
    'case-block'                     : 'block',
    'type-guard-block'               : 'block',
    'where-block'                    : 'block',
    'do-block'                       : 'block',
    'block-construct'                : 'block',

    'pp-branch'                      : 'pp',
    'pp-branch-do'                   : 'pp',
    'pp-branch-end-do'               : 'pp',
    'pp-branch-if'                   : 'pp',
    'pp-branch-end-if'               : 'pp',
    'pp-branch-forall'               : 'pp',
    'pp-branch-end-forall'           : 'pp',
    'pp-branch-select'               : 'pp',
    'pp-branch-end-select'           : 'pp',
    'pp-branch-where'                : 'pp',
    'pp-branch-end-where'            : 'pp',
    'pp-branch-pu'                   : 'pp',
    'pp-branch-end-pu'               : 'pp',
    'pp-branch-function'             : 'pp',
    'pp-branch-end-function'         : 'pp',
    'pp-branch-subroutine'           : 'pp',
    'pp-branch-end-subroutine'       : 'pp',

    'pp-section-elif'                : 'pp',
    'pp-section-else'                : 'pp',
    'pp-section-if'                  : 'pp',
    'pp-section-ifdef'               : 'pp',
    'pp-section-ifndef'              : 'pp',

    'mpi-call'                       : 'mpi',

    'call-stmt*'                     : 'call*'
}

def get_root_entities(full=False):
    s = set(['main-program'])
    if full:
        s |= set([
            'subroutine-external-subprogram',
            'subroutine-module-subprogram',
            'function-external-subprogram',
            'function-module-subprogram',
        ])
    return s

#

def is_compiler_directive(cats):
    b = False
    for cat in cats:
        if cat[0:4] in ('omp-', 'acc-', 'ocl-', 'xlf-', 'dec-'):
            b = True
            break
    return b

#

Q_AA_IN_LOOP_F = '''DEFINE input:inference "ont.cpi"
PREFIX f:   <%(f_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?loop ?aa ?pn ?dtor ?dtor_loc
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?pn ?aa ?loop ?pu_name ?vpu_name ?loc ?ver
    WHERE {

      ?pn a f:PartName ;
          src:parent ?aa .

      ?aa a f:ArrayAccess ;
          f:inDoConstruct ?loop .

      ?loop a f:DoConstruct ;
            f:inProgramUnitOrSubprogram ?pu_or_sp ;
            f:inProgramUnit ?pu .

      ?pu_or_sp src:inFile/src:location ?loc .

      ?pu a f:ProgramUnit ;
          src:inFile/src:location ?pu_loc ;
          ver:version ?ver .

      OPTIONAL {
        ?pu f:name ?pu_name
      }

      OPTIONAL {
        ?pu f:includedInProgramUnit ?vpu .
        ?vpu f:name ?vpu_name .
      }

    } GROUP BY ?pn ?aa ?loop ?pu_name ?vpu_name ?loc ?ver
  }

  OPTIONAL {
    ?pn f:declarator ?dtor .

    ?dtor a f:Declarator ;
          f:inProgramUnitOrFragment/src:inFile ?dtor_file .

    ?dtor_file a src:File ;
               src:location ?dtor_loc ;
               ver:version ?ver .
  }

}
}
''' % NS_TBL

Q_OTHER_CALLS_F = '''DEFINE input:inference "ont.cpi"
PREFIX f:   <%(f_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?sp ?sp_cat ?sub ?main ?prog ?call ?callee_name ?constr
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?pu ?pu_name ?vpu_name ?call ?callee_name
    WHERE {

      ?call a f:CallStmt ;
            f:name ?callee_name ;
            f:inProgramUnitOrSubprogram ?pu_or_sp ;
            f:inProgramUnit ?pu .

      ?pu_or_sp src:inFile/src:location ?loc .

      ?pu a f:ProgramUnit ;
          src:inFile/src:location ?pu_loc ;
          ver:version ?ver .

      OPTIONAL {
        ?pu f:name ?pu_name
      }

      OPTIONAL {
        ?pu f:includedInProgramUnit ?vpu .
        ?vpu f:name ?vpu_name .
      }

      FILTER NOT EXISTS {
        ?call f:mayCall ?callee .
      }

    } GROUP BY ?ver ?loc ?pu ?pu_name ?vpu_name ?call ?callee_name
  }

  OPTIONAL {
    ?call f:inSubprogram ?sp .
    ?sp a f:Subprogram ;
        a ?sp_cat0 OPTION (INFERENCE NONE) ;
        f:name ?sub .

    FILTER NOT EXISTS {
      ?call f:inSubprogram ?sp0 .
      ?sp0 f:inSubprogram ?sp .
      FILTER (?sp != ?sp0)
    }

    GRAPH <http://codinuum.com/ont/cpi> {
      ?sp_cat0 rdfs:label ?sp_cat
    }
  }

  OPTIONAL {
    ?call f:inContainerUnit ?constr .
    ?constr a f:ContainerUnit .
    FILTER EXISTS {
      {
        ?constr f:inProgramUnit ?pu .
        FILTER NOT EXISTS {
          ?call f:inSubprogram/f:inContainerUnit ?constr .
        }
      }
      UNION
      {
        ?call f:inSubprogram ?sp0 .
        ?constr f:inSubprogram ?sp0 .
      }
    }
    FILTER NOT EXISTS {
      ?c a f:ContainerUnit ;
         f:inContainerUnit ?constr .
      ?call f:inContainerUnit ?c .
      FILTER (?c != ?constr)
    }
  }

  OPTIONAL {
    ?call f:inMainProgram ?main .
    ?main a f:MainProgram .
    OPTIONAL {
      ?main f:name ?prog .
    }
  }

}
}
''' % NS_TBL

Q_DIRECTIVES_F = '''DEFINE input:inference "ont.cpi"
PREFIX f:   <%(f_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?sp ?sp_cat ?sub ?main ?prog ?dtv ?cat ?constr
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?pu ?pu_name ?vpu_name ?dtv ?cat
    WHERE {

      ?dtv a f:CompilerDirective ;
           a ?cat0 OPTION (INFERENCE NONE) ;
           f:inProgramUnitOrSubprogram ?pu_or_sp ;
           f:inProgramUnit ?pu .

      ?pu_or_sp src:inFile/src:location ?loc .

      ?pu a f:ProgramUnit ;
          src:inFile/src:location ?pu_loc ;
          ver:version ?ver .

      OPTIONAL {
        ?pu f:name ?pu_name
      }

      OPTIONAL {
        ?pu f:includedInProgramUnit ?vpu .
        ?vpu f:name ?vpu_name .
      }

      GRAPH <http://codinuum.com/ont/cpi> {
        ?cat0 rdfs:label ?cat .
      }

    } GROUP BY ?ver ?loc ?pu ?pu_name ?vpu_name ?dtv ?cat
  }

  OPTIONAL {
    ?dtv f:inSubprogram ?sp .
    ?sp a f:Subprogram ;
        a ?sp_cat0 OPTION (INFERENCE NONE) ;
        f:name ?sub .

    FILTER NOT EXISTS {
      ?dtv f:inSubprogram ?sp0 .
      ?sp0 f:inSubprogram ?sp .
      FILTER (?sp != ?sp0)
    }

    GRAPH <http://codinuum.com/ont/cpi> {
      ?sp_cat0 rdfs:label ?sp_cat
    }
  }

  OPTIONAL {
    ?dtv f:inContainerUnit ?constr .
    ?constr a f:ContainerUnit .
    FILTER EXISTS {
      {
        ?constr f:inProgramUnit ?pu .
        FILTER NOT EXISTS {
          ?dtv f:inSubprogram/f:inContainerUnit ?constr .
        }
      }
      UNION
      {
        ?dtv f:inSubprogram ?sp0 .
        ?constr f:inSubprogram ?sp0 .
      }
    }
    FILTER NOT EXISTS {
      ?c a f:ContainerUnit ;
         f:inContainerUnit ?constr .
      ?dtv f:inContainerUnit ?c .
      FILTER (?c != ?constr)
    }
  }

  OPTIONAL {
    ?dtv f:inMainProgram ?main .
    ?main a f:MainProgram .
    OPTIONAL {
      ?main f:name ?prog .
    }
  }

}
}
''' % NS_TBL

Q_CONSTR_CONSTR_F = '''DEFINE input:inference "ont.cpi"
PREFIX f:   <%(f_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?sp ?sp_cat ?sub ?main ?prog 
?constr ?cat
?parent_constr ?parent_cat ?parent_sub ?parent_prog ?parent_pu_name ?parent_vpu_name
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?pu ?pu_name ?vpu_name ?constr
    WHERE {

      ?constr a f:ContainerUnit ;
              f:inProgramUnitOrSubprogram ?pu_or_sp ;
              f:inProgramUnit ?pu .

      ?pu_or_sp src:inFile/src:location ?loc .

      ?pu a f:ProgramUnit ;
          src:inFile/src:location ?pu_loc ;
          ver:version ?ver .

      OPTIONAL {
        ?pu f:name ?pu_name
      }

      OPTIONAL {
        ?pu f:includedInProgramUnit ?vpu .
        ?vpu f:name ?vpu_name .
      }

    } GROUP BY ?ver ?loc ?pu ?pu_name ?vpu_name ?constr
  }

  OPTIONAL {
    SELECT DISTINCT ?constr (GROUP_CONCAT(DISTINCT ?c; SEPARATOR="&") AS ?cat)
    WHERE {
      ?constr a ?cat0 OPTION (INFERENCE NONE) .

      GRAPH <http://codinuum.com/ont/cpi> {
        ?cat0 rdfs:label ?c .
      }
    } GROUP BY ?constr
  }

  OPTIONAL {
    ?constr f:inSubprogram ?sp .
    ?sp a f:Subprogram ;
        a ?sp_cat0 OPTION (INFERENCE NONE) ;
        f:name ?sub .

    FILTER NOT EXISTS {
      ?constr f:inSubprogram ?sp0 .
      ?sp0 f:inSubprogram ?sp .
      FILTER (?sp != ?sp0)
    }

    # FILTER NOT EXISTS {
    #   ?constr f:inMainProgram ?m0 .
    #   ?m0 f:inContainerUnit ?parent_constr .
    #   FILTER (?m0 != ?constr && ?m0 != ?parent_constr)
    # }

    GRAPH <http://codinuum.com/ont/cpi> {
      ?sp_cat0 rdfs:label ?sp_cat .
    }
  }

  OPTIONAL {
    ?constr f:inMainProgram ?main .
    ?main a f:MainProgram .
    OPTIONAL {
      ?main f:name ?prog .
    }    
  }

  OPTIONAL {
    ?constr f:inContainerUnit ?parent_constr .
    ?parent_constr a f:ContainerUnit .

    FILTER (?constr != ?parent_constr)

    FILTER NOT EXISTS {
      ?constr f:inContainerUnit ?p0 .
      ?p0 a f:ContainerUnit ;
          f:inContainerUnit ?parent_constr .
      FILTER (?p0 != ?constr && ?p0 != ?parent_constr)
    }

    FILTER NOT EXISTS {
      ?constr f:inSubprogram ?sp0 .
      ?sp0 f:inContainerUnit ?parent_constr .
      FILTER (?sp0 != ?constr && ?sp0 != ?parent_constr)
    }

    {
      SELECT DISTINCT ?parent_constr (GROUP_CONCAT(DISTINCT ?c0; SEPARATOR="&") AS ?parent_cat)
      WHERE {
        ?parent_constr a ?parent_cat0 OPTION (INFERENCE NONE) .

        GRAPH <http://codinuum.com/ont/cpi> {
          ?parent_cat0 rdfs:label ?c0 .
        }
      } GROUP BY ?parent_constr
    }

    OPTIONAL {
      ?parent_constr f:inProgramUnit ?parent_pu .
      ?parent_pu f:name ?parent_pu_name .
    }

    OPTIONAL {
      ?parent_constr f:inProgramUnit/f:includedInProgramUnit ?parent_vpu .
      ?parent_vpu f:name ?parent_vpu_name .
    }

    OPTIONAL {
      ?parent_constr f:inMainProgram ?parent_main .
      ?parent_main a f:MainProgram .
      OPTIONAL {
        ?parent_main f:name ?parent_prog .
      }
    }

    OPTIONAL {
      ?parent_constr f:inSubprogram ?parent_sp .
      ?parent_sp a f:Subprogram ;
                 f:name ?parent_sub .

      FILTER NOT EXISTS {
        ?parent_constr f:inSubprogram ?sp0 .
        ?sp0 f:inSubprogram ?parent_sp .
        FILTER (?parent_sp != ?sp0)
      }
    }
  }

}
}
''' % NS_TBL

Q_CONSTR_SP_F = '''DEFINE input:inference "ont.cpi"
PREFIX f:   <%(f_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?sp ?sp_cat ?sub ?main ?prog
?constr ?cat ?call ?call_cat
?callee ?callee_name ?callee_loc ?callee_cat ?callee_pu_name
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?constr ?callee ?cat ?call ?call_cat
    WHERE {

      ?call a ?call_cat0 OPTION (INFERENCE NONE) ;
            f:inContainerUnit ?constr ;
            f:mayCall ?callee .

      FILTER (?call_cat0 IN (f:CallStmt, f:FunctionReference, f:PartName))

      ?constr a f:ContainerUnit ;
              a ?cat0 OPTION (INFERENCE NONE) ;
              f:inProgramUnitOrSubprogram ?pu_or_sp ;
              f:inProgramUnit ?pu .

      ?pu_or_sp src:inFile/src:location ?loc .

      FILTER NOT EXISTS {
        ?c a f:ContainerUnit ;
           f:inContainerUnit+ ?constr .
        ?call f:inContainerUnit+ ?c .
        FILTER (?c != ?constr)
      }

      ?pu a f:ProgramUnit ;
          ver:version ?ver ;
          src:inFile/src:location ?pu_loc .

      OPTIONAL {
        ?pu f:name ?pu_name
      }

      OPTIONAL {
        ?pu f:includedInProgramUnit ?vpu .
        ?vpu f:name ?vpu_name .
      }

      GRAPH <http://codinuum.com/ont/cpi> {
        ?cat0 rdfs:label ?cat .
        ?call_cat0 rdfs:label ?call_cat .
      }

    } GROUP BY ?ver ?loc ?pu_name ?vpu_name ?constr ?callee ?cat ?call ?call_cat
  }

  {
    SELECT DISTINCT ?callee ?callee_cat ?callee_loc ?ver ?callee_pu_name
    (GROUP_CONCAT(DISTINCT ?cn; SEPARATOR=":") AS ?callee_name)
    WHERE {

      ?callee a f:Subprogram ;
              a ?callee_cat0 OPTION (INFERENCE NONE) ;
              f:name ?cn ;
              src:inFile ?callee_file .

      ?callee_file a src:File ;
                   src:location ?callee_loc ;
                   ver:version ?ver .
      
      GRAPH <http://codinuum.com/ont/cpi> {
        ?callee_cat0 rdfs:label ?callee_cat
      }

      OPTIONAL {
        ?callee f:inProgramUnit/f:name ?callee_pu_name .
      }
    
    } GROUP BY ?callee ?callee_cat ?callee_loc ?ver ?callee_pu_name
  }

  OPTIONAL {
    ?constr f:inSubprogram ?sp .
    ?sp a f:Subprogram ;
        a ?sp_cat0 OPTION (INFERENCE NONE) ;
        f:name ?sub .

    FILTER NOT EXISTS {
      ?constr f:inSubprogram ?sp0 .
      ?sp0 f:inSubprogram ?sp .
      FILTER (?sp != ?sp0)
    }

    GRAPH <http://codinuum.com/ont/cpi> {
      ?sp_cat0 rdfs:label ?sp_cat
    }
  }

  OPTIONAL {
    ?constr f:inMainProgram ?main .
    ?main a f:MainProgram .
    OPTIONAL {
      ?main f:name ?prog .
    }    
  }

}
}
''' % NS_TBL

Q_SP_SP_F = '''DEFINE input:inference "ont.cpi"
PREFIX f:   <%(f_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?sp ?sp_cat ?sub ?main ?prog 
?callee ?callee_name ?callee_loc ?callee_cat ?call ?call_cat ?constr ?callee_pu_name
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?pu ?pu_name ?vpu_name ?callee ?call ?call_cat
    WHERE {

      ?call a ?call_cat0 OPTION (INFERENCE NONE) ;
            f:inProgramUnitOrSubprogram ?pu_or_sp ;
            f:inProgramUnit ?pu ;
            f:mayCall ?callee .

      ?pu_or_sp src:inFile/src:location ?loc .

      ?pu a f:ProgramUnit ;
          src:inFile/src:location ?pu_loc ;
          ver:version ?ver .

      OPTIONAL {
        ?pu f:name ?pu_name
      }

      OPTIONAL {
        ?pu f:includedInProgramUnit ?vpu .
        ?vpu f:name ?vpu_name .
      }

      FILTER (?call_cat0 IN (f:CallStmt, f:FunctionReference, f:PartName))

      FILTER NOT EXISTS {
        ?call f:inContainerUnit [] .
      }

      GRAPH <http://codinuum.com/ont/cpi> {
        ?call_cat0 rdfs:label ?call_cat .
      }

    } GROUP BY ?ver ?loc ?pu ?pu_name ?vpu_name ?callee ?call ?call_cat
  }

  {
    SELECT DISTINCT ?callee ?callee_cat ?callee_loc ?ver ?callee_pu_name
    (GROUP_CONCAT(DISTINCT ?cn; SEPARATOR=":") AS ?callee_name)
    WHERE {

      ?callee a f:Subprogram ;
              a ?callee_cat0 OPTION (INFERENCE NONE) ;
              f:name ?cn ;
              src:inFile ?callee_file .

      ?callee_file a src:File ;
                   src:location ?callee_loc ;
                   ver:version ?ver .
      
      GRAPH <http://codinuum.com/ont/cpi> {
        ?callee_cat0 rdfs:label ?callee_cat
      }

      OPTIONAL {
        ?callee f:inProgramUnit/f:name ?callee_pu_name .
      }

    } GROUP BY ?callee ?callee_cat ?callee_loc ?ver ?callee_pu_name
  }

  OPTIONAL {
    ?call f:inSubprogram ?sp .
    ?sp a f:Subprogram ;
        a ?sp_cat0 OPTION (INFERENCE NONE) ;
        f:name ?sub .

    FILTER NOT EXISTS {
      ?call f:inSubprogram ?sp0 .
      ?sp0 f:inSubprogram ?sp .
      FILTER (?sp != ?sp0)
    }

    GRAPH <http://codinuum.com/ont/cpi> {
      ?sp_cat0 rdfs:label ?sp_cat
    }
  }

  OPTIONAL {
    ?call f:inMainProgram ?main .
    ?main a f:MainProgram .
    OPTIONAL {
      ?main f:name ?prog .
    }    
  }

}
}
''' % NS_TBL

Q_CONSTR_QSPN_F = '''DEFINE input:inference "ont.cpi"
PREFIX f:   <%(f_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?qspn ?constr
WHERE {
GRAPH <%%(proj)s> {
  {
    SELECT DISTINCT ?ver ?loc ?pu_name ?vpu_name ?sp0 ?constr
    (GROUP_CONCAT(DISTINCT CONCAT(STR(?dist), ?n); SEPARATOR=",") AS ?qspn)
    WHERE {

      ?constr a f:ContainerUnit ;
              f:inSubprogram ?sp0 ;
              f:inProgramUnit ?pu .

      ?sp0 src:inFile/src:location ?loc .

      FILTER NOT EXISTS {
        ?constr f:inSubprogram/f:inSubprogram ?sp0 .
      }

      ?pu a f:ProgramUnit ;
          src:inFile/src:location ?pu_loc ;
          ver:version ?ver .

      OPTIONAL {
        ?pu f:name ?pu_name .
      }

      OPTIONAL {
        ?pu f:includedInProgramUnit ?vpu .
        ?vpu f:name ?vpu_name .
      }

      ?sp0 a f:Subprogram ;
           f:name ?sp0_name .

      ?spx f:name ?n .

      {
        SELECT ?x ?sp
        WHERE {
          ?x a f:Subprogram ;
             f:inSubprogram ?sp .
        }
      } OPTION(TRANSITIVE,
               T_IN(?x),
               T_OUT(?sp),
               T_DISTINCT,
               T_MIN(0),
               T_NO_CYCLES,
               T_STEP (?x) AS ?spx,
               T_STEP ('step_no') AS ?dist
               )
      FILTER (?x = ?sp0)

    } GROUP BY ?ver ?loc ?sp0 ?constr ?pu_name ?vpu_name
  }
}
}
''' % NS_TBL


QUERY_TBL = { 'fortran':
              { 
                  'aa_in_loop'    : Q_AA_IN_LOOP_F,
                  'other_calls'   : Q_OTHER_CALLS_F,
                  'directives'    : Q_DIRECTIVES_F,
                  'constr_constr' : Q_CONSTR_CONSTR_F,
                  'constr_sp'     : Q_CONSTR_SP_F,
                  'sp_sp'         : Q_SP_SP_F,
                  'constr_qspn'   : Q_CONSTR_QSPN_F,
              },
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


def get_url(x):
    u = pathname2url(os.path.join(os.pardir, x))
    return u



class IdGenerator(dp.base):
    def __init__(self, prefix=''):
        self._prefix = prefix
        self._count = 0

    def gen(self):
        i = '%s%x' % (self._prefix, self._count)
        self._count += 1
        return i

class IndexGenerator(dp.base):
    def __init__(self, init=0):
        self._count = init

    def gen(self):
        i = self._count
        self._count += 1
        return i

def node_list_to_string(l):
    return '\n'.join([str(x) for x in l])

def index(idx_gen, data, callees_tbl):

    def scan(d):
        children = d['children']
        for c in children:
            scan(c)
        i = idx_gen.gen()
        d['idx'] = i
        if children:
            d['lmi'] = children[0]['lmi']
        else:
            d['lmi'] = i

        if children == [] and callees_tbl:
            callee_name = d.get('callee', None)
            if callee_name:
                callees = callees_tbl.get(callee_name, [])
                if callees:
                    d['nlinks'] = len(callees)

    scan(data)

class Node(dp.base):
    def __init__(self, ver, loc, uri, cat='',
                 prog=None, sub=None,
                 callee_name=None, pu_name=None, vpu_name=None,
                 all_sps=False):

        self.relevant = False
        self.ver = ver
        self.loc = loc
        self.uri = uri
        self.cat = cat
        if cat != None:
            self.cats = set(cat.split('&'))
        else:
            self.warning('None cat: %s:%s:%s' % (get_localname(ver), loc, get_localname(uri)))
            self.cats = set()

        self.prog = prog
        self.sub = sub
        self.pu_name = pu_name
        self.vpu_name = vpu_name

        self.key = (ver, loc, get_localname(uri))

        self._ent = None
        self._fid = None
        self._start_line = None
        self._end_line = None

        self._parents = set()
        self._children = set()

        self.ancestors = set()
        self.descendants = set()

        self._callee_name = callee_name

        self._mkey = None

        self._container = None
        self._parents_in_container = set() # exclude self
        self._nparent_loops_in_container = None
        self._max_chain = None

        self._all_sps = all_sps


    def __eq__(self, other):
        if isinstance(other, Node):
            e = self.uri == other.uri
        else:
            e = False
        return e

    def __ne__(self, other):
        e = not self.__eq__(other)
        return e

    def __cmp__(self, other):
        l0 = self.get_start_line()
        l1 = other.get_start_line()
        c = cmp(l0, l1)
        return c

    def __hash__(self):
        return hash(self.key)

    def __str__(self):
        pu = self.get_pu()
        sl = self.get_start_line()
        el = self.get_end_line()
        if sl == el:
            r = '%d' % sl
        else:
            r = '%d-%d' % (sl, el)

        s = '%s[%s:%s:%s:%s]' % (self.cat, r, self.sub, pu, os.path.basename(self.loc))

        return s

    def is_relevant(self):
        b = False
        if self.cats & LOOPS:
            b = True
        elif self.cats & CALLS:
            if self._all_sps:
                b = True
            else:
                m = MARKER_CALLEE_PAT.match(self._callee_name)
                if m:
                    b = True
                else:
                    b = self._callee_name.startswith('mpi_')
        return b

    def count_parent_loops_in_container(self):
        if self._nparent_loops_in_container == None:
            ps = self.get_parents_in_container()
            count = 0
            for p in ps:
                if 'do-construct' in p.cats:
                    count += 1
            self._nparent_loops_in_container = count

            self.debug('%s <- {%s}' % (self, ';'.join(str(x) for x in ps)))

        return self._nparent_loops_in_container

    def get_parents_in_container(self):
        self.get_container()
        return self._parents_in_container

    def get_container(self): # subprog or main
        if not self._container:
            if self.cats & SUBPROGS or 'main-program' in self.cats:
                self._container = self
            else:
                if len(self._parents) == 1:
                    p = list(self._parents)[0]
                    self._container = p.get_container()
                    self._parents_in_container.add(p)
                    self._parents_in_container.update(p.get_parents_in_container())

                else:
                    if 'pp' not in [TYPE_TBL.get(c, None) for c in self.cats]:
                        pstr = ', '.join([str(p) for p in self._parents])
                        self.warning('multiple parents:\n%s:\nparents=[%s]' % (self, pstr))

        return self._container


    def score_of_chain(self, chain):
        if chain:
            if 'main-program' in chain[-1].cats:
                score = 0

                for nd in chain:
                    if nd.cats & CALLS:
                        score += nd.count_parent_loops_in_container()

                self.debug('%d <- [%s]' % (score, ';'.join([str(x) for x in chain])))
            else:
                score = -1
        else:
            score = -1

        return score

    def get_max_chain(self, visited_containers=[]): # chain of call or subprog
        if self._max_chain == None:

            container = self.get_container()

            if container == None:
                pass

            elif container is self:
                if container in visited_containers:
                    raise Exit

                if 'main-program' in container.cats:
                    self._max_chain = [self]

                elif container.cats & SUBPROGS:
                    calls = container.get_parents()

                    # if container.sub == 'abfl1x' or container.sub == 'abfl1':
                    #     print('!!! %s: calls: %s' % (container.sub, ', '.join([str(x) for x in calls])))

                    max_chain = []
                    in_file_call = False
                    start_line = sys.maxint
                    loc = None

                    skip_count = 0

                    for call in calls:
                        callc = call.get_container()

                        # if container.sub == 'abfl1x' or container.sub == 'abfl1':
                        #     print('!!! %s: callc: %s' % (container.sub, callc))

                        if callc:
                            try:
                                chain = callc.get_max_chain(visited_containers+[container])
                            except Exit:
                                skip_count += 1
                                continue

                            if container in chain:
                                pass
                            else:
                                chain_ = [container, call] + chain

                                loc_ = call.loc

                                in_file_call_ = False
                                if chain:
                                    in_file_call_ = loc_ == container.loc

                                start_line_ = call.get_start_line()

                                score_ =  self.score_of_chain(chain_)

                                max_score = self.score_of_chain(max_chain)

                                # if container.sub == 'abfl1x' or container.sub == 'abfl1':
                                #     print('!!! %s: chain_: score=%d\n%s' % (container.sub, score_, '\n'.join([str(x) for x in chain_])))

                                cond0 = score_ > max_score
                                cond1 = score_ == max_score and in_file_call_ and not in_file_call
                                cond2 = score_ == max_score and loc == loc_ and start_line_ < start_line

                                self.debug('cond0:%s, cond1:%s, cond2:%s' % (cond0, cond1, cond2))

                                # if container.sub == 'abfl1x' or container.sub == 'abfl1':
                                #     print('!!! %s: cond0:%s, cond1:%s, cond2:%s' % (container.sub, cond0, cond1, cond2))

                                if cond0 or cond1 or cond2:
                                    max_chain = chain_
                                    in_file_call = in_file_call_
                                    start_line = start_line_
                                    loc = loc_

                    if skip_count < len(calls):
                        self._max_chain = max_chain
                    else:
                        return []

                else: # another root (e.g. pp-directive)
                    pass

            else: # container is not self
                self._max_chain = container.get_max_chain()

            #print('!!! %s -> %d' % (self, self.score_of_chain(self._max_chain)))
            # if self.cat in SUBPROGS and (self.sub == 'abfl1x' or container.sub == 'abfl1'):
            #     print('!!! MAX %s: score=%d\n%s' % (self.sub, self.score_of_chain(self._max_chain), '\n'.join([str(x) for x in self._max_chain])))

        return self._max_chain
        

    def get_mkey(self):
        if not self._mkey:
            self._mkey = (get_lver(self.ver), self.loc, str(self.get_start_line()))
        return self._mkey

    def get_pu(self):
        pu = self.pu_name
        if not pu:
            pu = self.prog
        return pu

    def get_vpu(self):
        return self.vpu_name

    def is_root(self):
        b = len(self._parents) == 0
        return b

    def is_leaf(self):
        b = len(self._children) == 0
        return b

    def get_parents(self):
        return self._parents

    def add_parent(self, parent):
        self._parents.add(parent)

    def get_children(self):
        return self._children

    def add_child(self, child):
        self._children.add(child)

    def get_ent(self):
        if not self._ent:
            self._ent = SourceCodeEntity(uri=self.uri)
        return self._ent

    def get_fid(self):
        if not self._fid:
            self._fid = self.get_ent().get_file_id().get_value()
        return self._fid

    def get_start_line(self):
        if not self._start_line:
            ent = self.get_ent()
            self._start_line = ent.get_range().get_start_line()
        return self._start_line

    def get_end_line(self):
        if not self._end_line:
            ent = self.get_ent()
            self._end_line = ent.get_range().get_end_line()
        return self._end_line

    def clear_ancestors(self):
        self.ancestors = set()

    def get_ancestors(self):
        if not self.ancestors:
            self.ancestors = set([self])
            self._iter_ancestors(self.ancestors)
        return self.ancestors

    def _iter_ancestors(self, ancs):
        for x in self._parents - ancs:
            ancs.add(x)
            x._iter_ancestors(ancs)

    def clear_descendants(self):
        self.descendants = set()

    def get_descendants(self):
        if not self.descendants:
            self.descendants = set([self])
            self._iter_descendants(self.descendants)
        return self.descendants

    def _iter_descendants(self, decs):
        for x in self._children - decs:
            decs.add(x)
            x._iter_descendants(decs)

    def get_type(self):
        ty = None
        for c in self.cats:
            if c.startswith('omp-'):
                ty = 'omp'
                break
            elif c.startswith('acc-'):
                ty = 'acc'
                break
            elif c.startswith('dec-'):
                ty = 'dec'
                break
            elif c.startswith('xlf-'):
                ty = 'xlf'
                break
            elif c.startswith('ocl-'):
                ty = 'ocl'
                break

            ty = TYPE_TBL.get(c, None)
            if ty:
                break
        return ty

    def is_construct(self):
        b = False
        for c in self.cats:
            if c.endswith('-construct'):
                b = True
                break
        return b

    def is_pp(self):
        b = False
        for c in self.cats:
            if c.startswith('pp-'):
                b = True
                break
        return b

    def is_block(self):
        b = False
        for c in self.cats:
            if c.endswith('-block'):
                b = True
                break
        return b

    def get_block_cat(self):
        cat = None
        for c in self.cats:
            if c.endswith('-block'):
                cat = c
                break
        return cat

    def is_constr_head(self, child):
        b = all([self.is_construct(),
                 self.get_start_line() == child.get_start_line(),
                 not child.is_pp(),
                 not child.is_construct(),
                 not child.is_block()])
        return b

    def is_constr_tail(self, child):
        b = all([self.is_construct(),
                 self.get_end_line() == child.get_end_line(),
                 not child.is_construct(),
                 not child.is_block()])
        return b

    def to_dict(self, ancl, ntbl,
                elaborate=None,
                idgen=None,
                collapsed_caller_tbl={},
                expanded_callee_tbl={},
                parent_tbl=None,
                is_marked=None,
                omitted=set()):
        # ntbl: caller_name * subprog node * level -> visited

        ancl_ = ancl
        lv = len(ancl)

        if self.cats & SUBPROGS:
            self.debug('%s[%d:%s:%s:%s]' % (' '*lv,
                                            self.get_start_line(),
                                            self.sub,
                                            self.prog,
                                            self.loc))

            ancl_ = [self] + ancl
            if lv > 0:
                ntbl[(ancl[0].sub, self, lv)] = True
                self.debug('[REG] %s:%s:%d' % (ancl[0].sub, self.sub, lv))

        #TARGET_NAMES = ['fock_ffte', 'init_fock_ffte'] #!!!

        _children_l = sorted(list(self._children))

        children_l = filter(lambda c: c not in ancl and c.relevant, _children_l)

        # if self._callee_name in TARGET_NAMES:
        #     print('!!! %s' % self)
        #     print('!!! _children_l=%s' % (node_list_to_string(_children_l)))
        #     print('!!!  children_l=%s' % (node_list_to_string(children_l)))

        if children_l:
            if self.is_constr_head(children_l[0]):
                children_l = children_l[1:]

        if children_l:
            if self.is_constr_tail(children_l[-1]):
                children_l = children_l[:-1]

        is_caller = self.cats & CALLS

        is_filtered_out = False

        self.ignored_callee_count = 0

        if is_caller:
            ancl_ = [self] + ancl

            cand = filter(lambda c: c.loc == self.loc, children_l)
            if cand:
                children_l = cand

            def filt(c):
                max_chain = c.get_max_chain()

                if max_chain == None:
                    return False

                max_lv = len(max_chain)

                chain_ = [c] + ancl_
                lv_ = len(chain_)

                # if self._callee_name in TARGET_NAMES:
                #     print('!!! max_lv=%d lv_=%d' % (max_lv, lv_))
                #     print('!!! max_chain: %s' % node_list_to_string(max_chain))
                #     print('!!! chain_   : %s' % node_list_to_string(chain_))

                b = True

                if max_lv == lv_:
                    for i in range(lv_):
                        if chain_[i] != max_chain[i]:
                            b = False
                            # if c.sub == 'abfl1x':
                            #     print('!!! chain_: score=%d\n%s' % (c.score_of_chain(chain_), '\n'.join([str(x) for x in chain_])))

                            break
                else:
                    b = False

                self.debug('[LOOKUP] %s:%s:%s' % (self.sub, c, len(ancl_)))
                hit = ntbl.has_key((self.sub, c, len(ancl_)))

                b = b and (not hit)

                self.debug('[FILT] (%s->)%s (lv=%d) --> %s (hit=%s, max_lv=%d)' % (self.sub,
                                                                                   c.sub,
                                                                                   lv_,
                                                                                   b,
                                                                                   hit,
                                                                                   max_lv))
                return b

            # if self._callee_name in TARGET_NAMES:
            #     print('!!! 0 children_l=%s' % (node_list_to_string(children_l)))

            before = len(children_l)
            children_l = filter(filt, children_l)
            if before > len(children_l):
                is_filtered_out = True

            # if self._callee_name in TARGET_NAMES:
            #     print('!!! 1 children_l=%s' % (node_list_to_string(children_l)))

            def check_mark(nd):
                b = is_marked(nd)
                if not b and nd.cats & SUBPROGS:
                    self.ignored_callee_count += 1
                return b

            if is_marked:
                children_l = filter(check_mark, children_l)

            # if self._callee_name in TARGET_NAMES:
            #     print('!!! 2 children_l=%s' % (node_list_to_string(children_l)))

        # children = [c.to_dict(ancl_, ntbl,
        #                       elaborate=elaborate,
        #                       idgen=idgen,
        #                       parent_tbl=parent_tbl,
        #                       is_marked=is_marked) for c in children_l]

        children = []
        for c in children_l:
            x = c.to_dict(ancl_, ntbl,
                          elaborate=elaborate,
                          idgen=idgen,
                          collapsed_caller_tbl=collapsed_caller_tbl,
                          expanded_callee_tbl=expanded_callee_tbl,
                          parent_tbl=parent_tbl,
                          is_marked=is_marked,
                          omitted=omitted)

            if omitted & c.cats:
                #print('!!! %s (%d)' % (c, len(c.get_children())))
                children += x.get('children', [])
            else:
                children.append(x)

        # print('!!! %s (%d:%s -> %d)' % (self,
        #                                 len(self._children),
        #                                 '&'.join([c.cat for c in self._children]),
        #                                 len(children)))

        if is_caller and children != []:
            try:
                l = expanded_callee_tbl[self._callee_name]
                expanded_callee_tbl[self._callee_name] = l + [x for x in children if x not in l]
            except KeyError:
                expanded_callee_tbl[self._callee_name] = children

        d = {
            'cat'      : self.cat,
            'loc'      : self.loc,
            'pu'       : self.get_pu(),
            'sl'       : self.get_start_line(),
            'el'       : self.get_end_line(),
            'children' : children,
        }

        if self.ignored_callee_count:
            d['ignored_callee_count'] = self.ignored_callee_count

        vpu = self.get_vpu()
        if vpu:
            d['vpu'] = vpu

        if self._callee_name:
            d['callee'] = self._callee_name

        ty = self.get_type()
        if ty:
            d['type'] = ty

        if idgen:
            nid = idgen.gen()
            d['id'] = nid

            if parent_tbl != None:
                for c in d.get('children', []):
                    cid = c['id']
                    #print('!!! parent_tbl: %s(%s) -> %s(%s)' % (cid, c['cat'], nid, d['cat']))
                    parent_tbl[cid] = nid

            if is_caller and self._children != [] and children == [] and is_filtered_out:
                v = (d, len(ancl))
                try:
                    collapsed_caller_tbl[self._callee_name].append(v)
                except KeyError:
                    collapsed_caller_tbl[self._callee_name] = [v]

        if elaborate:
            if self.cats & omitted:
                pass
            else:
                elaborate(self, d)

        return d



class Exit(Exception):
    pass

def tbl_get_list(tbl, key):
    try:
        l = tbl[key]
    except KeyError:
        l = []
        tbl[key] = l
    return l

def tbl_get_set(tbl, key):
    try:
        s = tbl[key]
    except KeyError:
        s = set()
        tbl[key] = s
    return s

def tbl_get_dict(tbl, key):
    try:
        d = tbl[key]
    except KeyError:
        d = {}
        tbl[key] = d
    return d

def gen_conf_a(proj_id, ver, proj_dir=PROJECTS_DIR):
    dp.debug('generating conf for "%s" (ver=%s)' % (proj_id, ver))
    conf = Config()
    conf.proj_id = proj_id
    conf.proj_path = os.path.join(proj_dir, proj_id)
    conf.vkind = VKIND_VARIANT
    conf.vers = [ver]
    conf.nversions = 1
    conf.use_internal_parser()
    conf.finalize()
    return conf

    
def gen_conf(proj_id, commits=['HEAD'], proj_dir=None):
    dp.debug('generating conf for "%s" (commits=[%s])' % (proj_id,
                                                          ','.join(commits)))
    conf = Config()
    conf.proj_id = proj_id

    if proj_dir:
        conf.proj_path = os.path.join(proj_dir, re.sub(r'_git$', '', proj_id))

    conf.gitweb_proj_id = re.sub(r'_git$', '.git', proj_id)
    conf.vkind = VKIND_GITREV
    conf.vers = commits
    conf.nversions = len(commits)
    conf.use_internal_parser()
    conf.finalize()
    return conf



class SourceFiles(dp.base):
    def __init__(self, conf, gitrepo=GIT_REPO_BASE, proj_dir=PROJECTS_DIR):

        proj_id = conf.proj_id

        self.repo = None
        self.proj_dir = None
        
        if conf.is_vkind_gitrev():
            repo_path = os.path.normpath(os.path.join(gitrepo, conf.gitweb_proj_id))
            try:
                self.repo = Git2.Repository(repo_path)
            except:
                pid = re.sub(r'_git$', '', proj_id)
                repo_path = os.path.normpath(os.path.join(gitrepo, pid))
                self.repo = Git2.Repository(repo_path)

        else:
            self.proj_dir = os.path.join(proj_dir, proj_id)


    def get_file(self, file_spec):
        lines = []

        try:

            if self.repo:
                blob = self.repo.get_blob(file_spec['fid']).data
                decoded = codecs.decode(blob, 'utf-8', 'replace')
                lines = decoded.splitlines()

            elif self.proj_dir:
                path = os.path.join(self.proj_dir, file_spec['ver_dir_name'], file_spec['path'])
                with codecs.open(path, encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()

        except Exception, e:
            self.warning(str(e))

        return lines


def norm_callee_name(orig):
    norm = orig
    if orig:
        norm = ':'.join(sorted(orig.split(':')))
    return norm

def is_x_dict(s, d):
    b = False
    cat = d.get('cat', None)
    if cat:
        if set(cat.split('&')) & s:
            b = True
    return b
def is_caller(d):
    return is_x_dict(CALLS, d)
def is_sp(d):
    return is_x_dict(SUBPROGS, d)

def iter_d(f, d, lv=0):
    f(lv, d)
    d_is_caller = is_caller(d)
    for c in d.get('children', []):
        lv_ = lv
        if d_is_caller and is_sp(c):
            lv_ = lv + 1
        iter_d(f, c, lv=lv_)

class Outline(dp.base):
    def __init__(self,
                 proj_id,
                 commits=['HEAD'],
                 method='odbc',
                 pw=VIRTUOSO_PW,
                 port=VIRTUOSO_PORT,
                 gitrepo=GIT_REPO_BASE,
                 proj_dir=PROJECTS_DIR,
                 ver='unknown',
                 simple_layout=False,
                 all_sps=False):

        self._proj_id = proj_id
        self._graph_uri = FB_NS + proj_id
        self._sparql = sparql.get_driver(method, pw=pw, port=port)
        self._method = method
        self._pw = pw
        self._port = port
        self._gitrepo = gitrepo
        self._proj_dir = proj_dir

        self._outline_dir = os.path.join(OUTLINE_DIR, self._proj_id)
        self._metrics_dir = os.path.join(METRICS_DIR, self._proj_id)

        self._simple_layout = simple_layout
        self._all_sps = all_sps

        self._conf = project.get_conf(proj_id)
        if not self._conf:
            if proj_id.endswith('_git'):
                self._conf = gen_conf(proj_id, commits=commits, proj_dir=gitrepo)
            else:
                self._conf = gen_conf_a(proj_id, ver, proj_dir)

        self._hash_algo = self._conf.hash_algo

        self._tree_tbl = {} # lang -> tree

        self._node_tbl = {} # (ver * loc * uri) -> node

        self._lines_tbl = {} # ver -> loc -> line set
        self._fid_tbl = {} # (ver * loc) -> fid

        self._metrics = None

        self._marked_nodes = set()

        self._aa_tbl = {} # lang -> (ver * loc * start_line) -> range list
        self._qspn_tbl = {} # lang -> (ver * loc * start_line) -> name list


    def setup_aa_tbl(self): # assumes self._node_tbl
        if not self._aa_tbl:
            self.message('setting up array reference table...')
            for lang in QUERY_TBL.keys():

                tbl = {}

                query = QUERY_TBL[lang]['aa_in_loop'] % {'proj':self._graph_uri}

                for qvs, row in self._sparql.query(query):
                    ver  = row['ver']
                    loc  = row['loc']
                    loop = row['loop']
                    pn   = row['pn']

                    pu_name = row.get('pu_name', None)
                    vpu_name = row.get('vpu_name', None)
                    dtor = row.get('dtor', None)

                    lver = get_lver(ver)

                    loop_node = self.get_node(Node(ver, loc, loop,
                                                   cat='do-construct',
                                                   pu_name=pu_name,
                                                   vpu_name=vpu_name))

                    pns = tbl_get_list(tbl, loop_node.get_mkey())

                    pn_ent = SourceCodeEntity(uri=pn)
                    r = pn_ent.get_range()
                    st = {'line':r.get_start_line(),'ch':r.get_start_col()}
                    ed = {'line':r.get_end_line(),'ch':r.get_end_col()}
                    d = {'start':st,'end':ed}

                    if dtor:
                        dtor_ent = SourceCodeEntity(uri=dtor)
                        dtor_fid = dtor_ent.get_file_id()

                        df = {'line':dtor_ent.get_range().get_start_line()}

                        if dtor_fid != pn_ent.get_file_id():
                            df['fid'] = dtor_fid.get_value()
                            df['path'] = row['dtor_loc']

                        d['def'] = df

                    pns.append(d)

                    for p in loop_node.get_parents_in_container():
                        if 'do-construct' in p.cats:
                            ppns = tbl_get_list(tbl, p.get_mkey())
                            ppns.append(d)

                self._aa_tbl[lang] = tbl



    def get_aref_ranges(self, lang, mkey):
        #self.setup_aa_tbl()
        rs = None
        try:
            rs = self._aa_tbl[lang][mkey]
        except KeyError:
            pass
        return rs


    def setup_qspn_tbl(self):
        if not self._qspn_tbl:
            self.message('setting up qualified subprogram name table...')
            for lang in QUERY_TBL.keys():

                tbl = {}

                query = QUERY_TBL[lang]['constr_qspn'] % {'proj':self._graph_uri}

                for qvs, row in self._sparql.query(query):
                    ver  = row['ver']
                    loc  = row['loc']
                    constr = row['constr']
                    qspn = row['qspn']

                    pu_name = row.get('pu_name', None)
                    #vpu_name = row.get('vpu_name', None)

                    lver = get_lver(ver)

                    constr_node = self.get_node(Node(ver, loc, constr))

                    l = [remove_leading_digits(x) for x in qspn.split(QN_SEP)]
                    l.reverse()
                    if l[0] == pu_name:
                        del l[0]
                    l.insert(0, pu_name)

                    tbl[constr_node.get_mkey()] = l

                self._qspn_tbl[lang] = tbl


    def get_max_loop_level(self, ent):
        m = self.get_metrics()
        lv = m.get_max_loop_level(ent)
        return lv

    def get_metrics(self):
        if not self._metrics:
            self.extract_metrics()
        return self._metrics

    def extract_metrics(self):
        if not self._metrics:
            self.message('extracting metrics...')
            self._metrics = Metrics(self._proj_id, self._method, pw=self._pw, port=self._port)
            self._metrics.calc()
            self.message('done.')

            try:
                for lang in QUERY_TBL.keys():
                    fop_tbl = self._metrics.get_item_tbl(lang, metrics.N_FP_OPS)
                    self.message('%s: fop_tbl has %d items' % (lang, len(fop_tbl)))
                    # for k in fop_tbl.keys():
                    #     print('!!! %s' % (k,))
                    aa0_tbl = self._metrics.get_item_tbl(lang, metrics.N_A_REFS[0])
                    self.message('%s: aa0_tbl has %d items' % (lang, len(aa0_tbl)))
            except KeyError:
                self.warning('could not find metrics')

    def get_metrics_tbl(self, lang, key):
        if not self._metrics:
            self.extract_metrics()

        ftbl = self._metrics.find_ftbl(lang, key)
        return ftbl

    def get_file_spec(self, verURI, path):
        spec = {}
        if self._conf.is_vkind_gitrev():
            spec['fid'] = self._fid_tbl[(verURI, path)]
        else:
            if self._simple_layout:
                spec['ver_dir_name'] = ''
            else:
                spec['ver_dir_name'] = self.get_ver_dir_name(verURI)
            spec['path'] = path

        return spec

    def get_line_text_tbl(self, source_files, verURI, strip=True):
        line_text_tbl = {} # loc -> line -> text

        lines_tbl = self._lines_tbl.get(verURI, {})

        for (loc, lines) in lines_tbl.iteritems():

            self.debug('scanning "%s"...' % loc)

            max_line = max(lines)

            text_tbl = tbl_get_dict(line_text_tbl, loc) # line -> text

            file_spec = self.get_file_spec(verURI, loc)

            ln = 0

            for l in source_files.get_file(file_spec):
                ln += 1

                if ln > max_line:
                    break

                if ln in lines:
                    if strip:
                        text_tbl[ln] = l.strip()
                    else:
                        text_tbl[ln] = l

        return line_text_tbl


    def get_vindex(self, uri):
        vi = None
        try:
            vi = self._conf.versionURIs.index(uri)
        except:
            pass
        return vi

    def get_ver_dir_name(self, verURI):
        v = self._conf.versions[self.get_vindex(verURI)]
        vdn = self._conf.get_ver_dir_name(v)
        return vdn

    def get_node(self, obj):
        node = self._node_tbl.get(obj.key, None)
        if not node:
            node = obj
            self._node_tbl[obj.key] = obj
        return node

    def mark_node(self, nd):
        self._marked_nodes.add(nd)
    
    def add_edge(self, lang, parent, child, mark=True):
        if parent is child:
            return

        p = self.get_node(parent)
        c = self.get_node(child)
        p.add_child(c)
        c.add_parent(p)

        # print('!!! %s(%d) -> %s(%d)' % (p,
        #                                 len(p.get_children()),
        #                                 c,
        #                                 len(c.get_children())))

        if mark and 'do-construct' in c.cats:
            mkey = c.get_mkey()
            try:
                mtbl = self.get_metrics_tbl(lang, mkey)
                bf0 = mtbl[metrics.BF[0]]
                bf1 = mtbl[metrics.BF[1]]
                bf2 = mtbl[metrics.BF[2]]
                if bf0 or bf1 or bf2:
                    self.mark_node(c)
                
            except KeyError:
                pass

        elif mark and self._all_sps and c.cats & SUBPROGS and p.cats & CALLS:
            self.mark_node(c)

    def get_tree(self, lang, callgraph=True, other_calls=True, directives=True, mark=True):
        t = self._tree_tbl.get(lang, None)
        if not t:
            self.message('constructing trees...')
            t = self.construct_tree(lang,
                                    callgraph=callgraph,
                                    other_calls=other_calls,
                                    directives=directives,
                                    mark=mark)
        return t

    def set_tree(self, lang, tree):
        self._tree_tbl[lang] = tree


    def setup_cg(self, mark=True):
        self.message('searching for call relations...')
        for lang in QUERY_TBL.keys():
            self.debug('sp_sp')
            query = QUERY_TBL[lang]['sp_sp'] % { 'proj' : self._graph_uri }

            for qvs, row in self._sparql.query(query):
                ver    = row['ver']
                loc    = row['loc']
                sp     = row.get('sp', None)
                sub    = row.get('sub', None)

                pu_name = row.get('pu_name', None)
                vpu_name = row.get('vpu_name', None)

                main  = row.get('main', None)
                prog  = None
                if main:
                    prog  = row.get('prog', '<main>')

                call     = row['call']
                call_cat = row['call_cat']

                callee_name = norm_callee_name(row['callee_name'])

                call_node = Node(ver, loc, call, cat=call_cat, prog=prog, sub=sub,
                                 callee_name=callee_name,
                                 pu_name=pu_name,
                                 vpu_name=vpu_name, all_sps=self._all_sps)

                parent_constr = row.get('constr', None)

                if sp:
                    sp_node = Node(ver, loc, sp, cat=row['sp_cat'],
                                   sub=sub, pu_name=pu_name, vpu_name=vpu_name)
                    if not parent_constr:
                        self.add_edge(lang, sp_node, call_node, mark=mark)

                if main:
                    main_node = Node(ver, loc, main, cat='main-program', prog=prog)
                    if not parent_constr and not sp:
                        self.add_edge(lang, main_node, call_node, mark=mark)

                callee      = row['callee']
                callee_loc  = row['callee_loc']
                callee_cat  = row['callee_cat']
                callee_pu_name = row.get('callee_pu_name', None)

                callee_node = Node(ver, callee_loc, callee, cat=callee_cat,
                                   sub=callee_name, pu_name=callee_pu_name)
                self.add_edge(lang, call_node, callee_node, mark=mark)

            self.debug('constr_sp')
            query = QUERY_TBL[lang]['constr_sp'] % { 'proj' : self._graph_uri }

            for qvs, row in self._sparql.query(query):
                ver    = row['ver']
                loc    = row['loc']
                constr = row['constr']
                constr_cat = row['cat']

                pu_name = row.get('pu_name', None)
                vpu_name = row.get('vpu_name', None)

                sp    = row.get('sp', None)
                sub   = row.get('sub', None)
                main  = row.get('main', None)
                prog  = None
                if main:
                    prog  = row.get('prog', '<main>')

                constr_node = Node(ver, loc, constr, cat=constr_cat,
                                   prog=prog, sub=sub,
                                   pu_name=pu_name, vpu_name=vpu_name)

                call     = row['call']
                call_cat = row['call_cat']

                callee_name = norm_callee_name(row['callee_name'])

                call_node = Node(ver, loc, call, cat=call_cat, prog=prog, sub=sub,
                                 callee_name=callee_name,
                                 pu_name=pu_name,
                                 vpu_name=vpu_name, all_sps=self._all_sps)

                self.add_edge(lang, constr_node, call_node, mark=mark)

                if call_node.is_relevant():
                    self._relevant_nodes.add(call_node)

                callee      = row['callee']
                callee_loc  = row['callee_loc']
                callee_cat  = row['callee_cat']
                callee_pu_name = row.get('callee_pu_name', None)

                callee_node = Node(ver, callee_loc, callee, cat=callee_cat,
                                   sub=callee_name, pu_name=callee_pu_name)
                self.add_edge(lang, call_node, callee_node, mark=mark)

        self.message('check marks...')
        a = set()
        for marked in self._marked_nodes:
            #print('!!! marked=%s' % marked)
            ancs = marked.get_ancestors()
            a.update(ancs)
                
        self._marked_nodes.update(a)


    def construct_tree(self, lang, callgraph=True, other_calls=True, directives=True, mark=True):

        self._relevant_nodes = set()

        self.debug('constr_constr')

        query = QUERY_TBL[lang]['constr_constr'] % { 'proj' : self._graph_uri }

        for qvs, row in self._sparql.query(query):
            ver    = row['ver']
            loc    = row['loc']
            sp     = row.get('sp', None)
            sub    = row.get('sub', None)
            constr = row['constr']
            cat    = row.get('cat', None)

            pu_name = row.get('pu_name', None)
            vpu_name = row.get('vpu_name', None)

            main  = row.get('main', None)
            prog  = None
            if main:
                prog  = row.get('prog', '<main>')

            constr_node = Node(ver, loc, constr, cat=cat,
                               prog=prog, sub=sub,
                               pu_name=pu_name, vpu_name=vpu_name)

            if constr_node.is_relevant():
                self._relevant_nodes.add(constr_node)

            parent_constr = row.get('parent_constr', None)

            if parent_constr:
                parent_sub = row.get('parent_sub', None)
                parent_prog = row.get('parent_prog', None)
                parent_pu_name = row.get('parent_pu_name', None)
                parent_vpu_name = row.get('parent_vpu_name', None)
                parent_cat = row.get('parent_cat', None)
                parent_node = Node(ver, loc, parent_constr, cat=parent_cat,
                                   prog=parent_prog, sub=parent_sub,
                                   pu_name=parent_pu_name,vpu_name=parent_vpu_name)
                self.add_edge(lang, parent_node, constr_node, mark=mark)
                if parent_node.is_relevant():
                    self._relevant_nodes.add(parent_node)

            elif sp:
                sp_node = Node(ver, loc, sp, cat=row['sp_cat'],
                               sub=sub, pu_name=pu_name, vpu_name=vpu_name)
                sp_flag = False
                self.add_edge(lang, sp_node, constr_node, mark=mark)

            elif main:
                main_node = Node(ver, loc, main, cat='main-program', prog=prog)
                main_flag = False
                self.add_edge(lang, main_node, constr_node, mark=mark)

        #

        if directives:

            self.debug('directives')

            query = QUERY_TBL[lang]['directives'] % { 'proj' : self._graph_uri }

            for qvs, row in self._sparql.query(query):
                ver    = row['ver']
                loc    = row['loc']
                sp     = row.get('sp', None)
                sub    = row.get('sub', None)
                dtv    = row['dtv']
                cat    = row.get('cat', None)

                pu_name = row.get('pu_name', None)
                vpu_name = row.get('vpu_name', None)

                main  = row.get('main', None)
                prog  = None
                if main:
                    prog  = row.get('prog', '<main>')

                dtv_node = Node(ver, loc, dtv, cat=cat,
                                prog=prog, sub=sub,
                                pu_name=pu_name, vpu_name=vpu_name)

                self._relevant_nodes.add(dtv_node)

                parent_constr = row.get('constr', None)
                if parent_constr:
                    self.add_edge(lang, Node(ver, loc, parent_constr), dtv_node,
                                  mark=mark)

                if sp:
                    sp_node = Node(ver, loc, sp, cat=row['sp_cat'],
                                   sub=sub, pu_name=pu_name, vpu_name=vpu_name)
                    if not parent_constr:
                        self.add_edge(lang, sp_node, dtv_node, mark=mark)

                if main:
                    main_node = Node(ver, loc, main, cat='main-program', prog=prog)
                    if not parent_constr and not sp:
                        self.add_edge(lang, main_node, dtv_node, mark=mark)

        #

        if other_calls:

            self.debug('other calls')

            query = QUERY_TBL[lang]['other_calls'] % { 'proj' : self._graph_uri }

            for qvs, row in self._sparql.query(query):
                ver    = row['ver']
                loc    = row['loc']
                sp     = row.get('sp', None)
                sub    = row.get('sub', None)
                call   = row['call']

                callee_name = row['callee_name']

                pu_name = row.get('pu_name', None)
                vpu_name = row.get('vpu_name', None)

                main  = row.get('main', None)
                prog  = None
                if main:
                    prog  = row.get('prog', '<main>')

                cat = 'call-stmt*'

                if callee_name.startswith('mpi_'):
                    cat = 'mpi-call'

                call_node = Node(ver, loc, call, cat=cat, prog=prog, sub=sub,
                                 callee_name=callee_name,
                                 pu_name=pu_name,
                                 vpu_name=vpu_name, all_sps=self._all_sps)

                if True or call_node.is_relevant():
                    self._relevant_nodes.add(call_node)

                parent_constr = row.get('constr', None)
                if parent_constr:
                    self.add_edge(lang, Node(ver, loc, parent_constr), call_node,
                                  mark=mark)

                if sp:
                    sp_node = Node(ver, loc, sp, cat=row['sp_cat'],
                                   sub=sub, pu_name=pu_name, vpu_name=vpu_name)
                    if not parent_constr:
                        self.add_edge(lang, sp_node, call_node, mark=mark)

                if main:
                    main_node = Node(ver, loc, main, cat='main-program', prog=prog)
                    if not parent_constr and not sp:
                        self.add_edge(lang, main_node, call_node, mark=mark)

        #

        if callgraph:
            self.setup_cg(mark=mark)

        roots = []

        count = 0

        self._lines_tbl = {}
        self._fid_tbl = {}

        self.setup_aa_tbl()
        self.setup_qspn_tbl()

        for k in self._node_tbl.keys():
            count += 1

            (v, _, _) = k

            node = self._node_tbl[k]

            if node.is_root():
                roots.append(node)

            lntbl = tbl_get_dict(self._lines_tbl, v)
            lines = tbl_get_set(lntbl, node.loc)

            for ln in range(node.get_start_line(), node.get_end_line()+1):
                lines.add(ln)

            if not (v, node.loc) in self._fid_tbl:
                fid = node.get_fid()
                self._fid_tbl[(v, node.loc)] = fid

            mkey = node.get_mkey() # register lines of definitions
            try:
                for pn in self._aa_tbl[lang][mkey]:
                    df = pn.get('def', None)
                    if df:
                        ln = df.get('line', None)
                        p = df.get('path', None)
                        fid = df.get('fid', None)
                        if ln and p:
                            lntbl = tbl_get_dict(self._lines_tbl, v)
                            lines = tbl_get_set(lntbl, p)
                            lines.add(ln)
                            if fid:
                                if not (v, p) in self._fid_tbl:
                                    self._fid_tbl[(v, p)] = fid

            except KeyError:
                pass

        self.message('%d root nodes (out of %d nodes) found' % (len(roots), count))

        # def dump(lv, k):
        #     print('!!! %s%s(%d) %s' % ('  '*lv, k,
        #                                len(k.get_children()),
        #                                ';'.join([c.cat for c in k.get_children()])))
        # for root in roots:
        #     self.iter_tree(root, dump)

        tree = {'node_tbl':self._node_tbl,'roots':roots}

        for nd in self._relevant_nodes:
            nd.relevant = True
            for a in nd.get_ancestors():
                a.relevant = True

        self.set_tree(lang, tree)

        self._node_tbl = {}

        return tree



    def iter_tree(self, root, f, pre=None, post=None):
        self.__iter_tree(0, root, f, pre=pre, post=post)

    def __iter_tree(self, lv, node, f, pre=None, post=None):
        if pre:
            pre(node)

        if f:
            f(lv, node)

        children = node.get_children()

        for child in children:
            if node != child:
                self.__iter_tree(lv+1, child, f, pre=pre, post=post)

        if post:
            post(node)

    def gen_topic_file_name(self):
        fn = TOPIC_FILE_FMT % self._proj_id
        return fn

    def gen_data_file_name(self, fid):
        fn = OUTLINE_FILE_FMT % fid
        return fn

    def gen_metrics_file_name(self, lver):
        fn = METRICS_FILE_FMT % lver
        return fn

    def get_measurement(self, mtbl, ms):
        d = {}
        for m in ms:
            v = mtbl[m]
            k = metrics.abbrv_tbl[m]
            d[k] = v
        return d

    def gen_topic(self, lang,
                  outdir='.', docsrc=None, index=None, model='lsi', ntopics=32):

        topic_dir = os.path.join(outdir, TOPIC_DIR)

        if not ensure_dir(topic_dir):
            return

        if index and docsrc:
            proj = re.sub(r'_git$', '', self._proj_id)
            dpath = os.path.join(docsrc, proj)
            self.message('reading from "%s"' % dpath)
            opath = os.path.join(topic_dir, self.gen_topic_file_name())
            search(index, model, dpath, ntopics=ntopics, lang=lang, outfile=opath)

    def mkrow(self, lver, loc, sub, lnum, mtbl, nid):
        tbl = mtbl.copy()
        tbl['proj']   = self._proj_id
        tbl['ver']    = lver
        tbl['path']   = loc
        tbl['sub']    = sub
        tbl['lnum']   = lnum
        tbl['digest'] = mtbl['meta']['digest']
        tbl['nid']    = nid
        row = []
        for k in METRICS_ROW_HEADER:
            if k != 'root_file':
                row.append(tbl[k])
        return row

    def gen_index_tables(self):
        path_list_tbl = {} # ver -> path list
        fid_list_tbl = {}  # ver -> fid list

        path_idx_tbl_tbl = {} # ver -> path -> idx
        fid_idx_tbl_tbl = {}  # ver -> fid -> idx

        vers = set()

        for ((ver, path), fid) in self._fid_tbl.iteritems():
            vers.add(ver)
            try:
                path_list = path_list_tbl[ver]
            except KeyError:
                path_list = []
                path_list_tbl[ver] = path_list

            try:
                fid_list = fid_list_tbl[ver]
            except KeyError:
                fid_list = []
                fid_list_tbl[ver] = fid_list

            try:
                path_idx_tbl = path_idx_tbl_tbl[ver]
            except KeyError:
                path_idx_tbl = {}
                path_idx_tbl_tbl[ver] = path_idx_tbl

            try:
                fid_idx_tbl = fid_idx_tbl_tbl[ver]
            except KeyError:
                fid_idx_tbl = {}
                fid_idx_tbl_tbl[ver] = fid_idx_tbl

            if path not in path_list:
                path_idx = len(path_list)
                path_list.append(path)
                path_idx_tbl[path] = path_idx

            if fid not in fid_list:
                fid_idx = len(fid_list)
                fid_list.append(fid)
                fid_idx_tbl[fid] = fid_idx

        self._path_list_tbl = path_list_tbl
        self._fid_list_tbl = fid_list_tbl

        self._path_idx_tbl_tbl = path_idx_tbl_tbl
        self._fid_idx_tbl_tbl = fid_idx_tbl_tbl


    def gen_data(self, lang, outdir='.', extract_metrics=True, omitted=set(), all_roots=False):

        outline_dir = os.path.join(outdir, self._outline_dir)
        outline_v_dir = os.path.join(outline_dir, 'v')

        if not ensure_dir(outline_v_dir):
            return

        if extract_metrics:
            self.extract_metrics()

        tree = self.get_tree(lang)

        self.gen_index_tables()

        root_tbl = {} # ver -> loc -> root (contains loop) list

        count = 0

        root_entities = get_root_entities(full=all_roots)

        # filter out trees that do not contain loops
        for root in tree['roots']:
            try:
                if root.cats & root_entities:
                    for x in root.get_descendants():
                        if 'do-construct' in x.cats:
                            raise Exit

            except Exit:
                count += 1

                loc_tbl = tbl_get_dict(root_tbl, root.ver)

                roots = tbl_get_list(loc_tbl, root.loc)

                roots.append(root)

        self.message('%d root nodes (main programs that contain loops) found' % count)

        metrics_dir = None

        if extract_metrics:
            self.extract_metrics()
            metrics_dir = os.path.join(outdir, self._metrics_dir)

        source_files = SourceFiles(self._conf, gitrepo=self._gitrepo, proj_dir=self._proj_dir)

        qspn_tbl = self._qspn_tbl[lang]

        for ver in root_tbl.keys():

            if ver not in self._conf.versionURIs:
                continue

            path_idx_tbl = self._path_idx_tbl_tbl.get(ver, {})
            fid_idx_tbl = self._fid_idx_tbl_tbl.get(ver, {})

            path_list = self._path_list_tbl.get(ver, [])
            fid_list = self._fid_list_tbl.get(ver, [])

            lver = get_lver(ver)

            loc_tbl = root_tbl[ver]

            json_ds = []
     
            self.message('generating line text table for "%s"...' % lver)

            line_text_tbl = self.get_line_text_tbl(source_files, ver)

            relevant_node_tbl = {} # loc -> lnum -> nid list
            nodes = set()
            csv_rows = []

            def reg_nid(loc, lnum, nid):
                try:
                    ltbl = relevant_node_tbl[loc]
                except KeyError:
                    ltbl = {}
                    relevant_node_tbl[loc] = ltbl
                try:
                    nids = ltbl[lnum]
                except KeyError:
                    nids = []
                    ltbl[lnum] = nids
                if nid not in nids:
                    nids.append(nid)

            def is_marked(node):
                b = node in self._marked_nodes
                return b

            def elaborate(node, d):
                fid = node.get_fid()
                loc = node.loc
                d['fid'] = fid_idx_tbl[fid]
                d['loc'] = path_idx_tbl[loc]

                start_line = node.get_start_line()
                if node.is_block():
                    d['code'] = '<span class="cat">%s</span>' % node.get_block_cat()
                else:
                    try:
                        code = line_text_tbl[loc][start_line]
                        d['code'] = code

                    except KeyError:
                        pass

                mkey = (lver, loc, str(start_line))

                try:
                    d['qspn'] = qspn_tbl[mkey]
                except KeyError:
                    pass

                aref_ranges = self.get_aref_ranges(lang, mkey)
                if aref_ranges:
                    for aref_range in aref_ranges:
                        df = aref_range.get('def', None)
                        if df:
                            ln = df.get('line', None)
                            p = df.get('path', None)
                            if ln and p:
                                try:
                                    df['code'] = line_text_tbl[p][ln]
                                except KeyError:
                                    pass
                            if df.has_key('fid'):
                                del df['fid']

                    d['aref_ranges'] = json.dumps(aref_ranges)
                    
                try:
                    mtbl = self.get_metrics_tbl(lang, mkey)

                    bf0 = round(mtbl[metrics.BF[0]], 2)
                    bf1 = round(mtbl[metrics.BF[1]], 2)
                    bf2 = round(mtbl[metrics.BF[2]], 2)

                    if bf0 > 0 or bf1 > 0 or bf2 > 0:
                        self.debug('%s: %s -> %3.2f|%3.2f|%3.2f' % (node.cat, mkey, bf0, bf1, bf2))

                        md = self.get_measurement(mtbl, [
                            metrics.N_BRANCHES,
                            metrics.N_STMTS,
                            metrics.N_FP_OPS,
                        ] + metrics.N_IND_A_REFS +
                            metrics.N_A_REFS +
                            metrics.N_DBL_A_REFS
                        )

                        d['bf0'] = bf0
                        d['bf1'] = bf1
                        d['bf2'] = bf2

                        d['other_metrics'] = md
                        d['relevant'] = True

                        nid = d['id']
                        reg_nid(d['loc'], d['sl'], nid)

                        if node not in nodes:
                            row = self.mkrow(lver, loc, node.sub, start_line, mtbl, nid)
                            csv_rows.append(row)
                        
                        nodes.add(node)

                except KeyError:
                    pass

            idgen = IdGenerator()

            nid_tbl = {}
            parent_tbl = {}

            root_collapsed_caller_tbl = {}
            root_expanded_callee_tbl = {}

            d_tbl = {}

            self.message('converting trees into JSON for "%s"...' % lver)

            for loc in loc_tbl.keys():

                ds = []

                fid = None

                for root in loc_tbl[loc]:
                    if not fid:
                        fid = root.get_fid()

                    collapsed_caller_tbl = {}
                    root_collapsed_caller_tbl[root] = collapsed_caller_tbl

                    expanded_callee_tbl = {}
                    root_expanded_callee_tbl[root] = expanded_callee_tbl

                    d = root.to_dict([root], {},
                                     elaborate=elaborate,
                                     idgen=idgen,
                                     collapsed_caller_tbl=collapsed_caller_tbl,
                                     expanded_callee_tbl=expanded_callee_tbl,
                                     parent_tbl=parent_tbl,
                                     is_marked=is_marked,
                                     omitted=omitted)
                    ds.append(d)

                    d_tbl[d['id']] = root

                nid = idgen.gen()

                for d in ds:
                    parent_tbl[d['id']] = nid

                loc_d = {
                    'id'          : nid,
                    'text'        : loc,
                    'loc'         : path_idx_tbl[loc],
                    'children'    : ds,
                    'fid'         : fid_idx_tbl[fid],
                    'cat'         : 'file',
                    'type'        : 'file',
                }

                nid_tbl[nid] = loc

                json_ds.append(loc_d)

            def copy_dict(d, hook=(lambda x: x), info={}):
                children = [copy_dict(c, hook=hook, info=info) for c in d['children']]
                try:
                    info['count'] += 1
                except KeyError:
                    pass
                copied = dict.copy(d)
                hook(copied)
                copied['children'] = children
                return copied

            root_callees_tbl = {}

            self.debug('* root_collapsed_caller_tbl:')
            for (r, collapsed_caller_tbl) in root_collapsed_caller_tbl.iteritems():
                self.debug('root=%s:' % r)

                while collapsed_caller_tbl:
                    new_collapsed_caller_tbl = {}

                    callees_tbl = {}
                    root_callees_tbl[r] = callees_tbl

                    for (callee, d_lv_list) in collapsed_caller_tbl.iteritems():

                        self.debug(' callee=%s' % callee)

                        expanded_callee_tbl = root_expanded_callee_tbl.get(r, {})
                        callee_dl = expanded_callee_tbl.get(callee, [])
                        if callee_dl:
                            callees_tbl[callee] = [d['id'] for d in callee_dl]
                            self.debug('callees_tbl: %s -> [%s]' % (callee, ','.join(callees_tbl[callee])))
                            self.debug(' -> skip')
                            continue

                        callee_dl = []
                        collapsed_caller_tbl_ = {}

                        for (r_, tbl) in root_expanded_callee_tbl.iteritems():
                            callee_dl = tbl.get(callee, [])
                            if callee_dl:
                                self.debug('%d callee dicts found in %s' % (len(callee_dl), r_))
                                collapsed_caller_tbl_ = root_collapsed_caller_tbl.get(r_, {})
                                break

                        if callee_dl:
                            nid_callee_lv_tbl = {}

                            for callee_d in callee_dl:
                                def chk(lv_, d):
                                    callee_ = d.get('callee', None)
                                    if callee_ and d.get('children', []) == []:
                                        d_lv_list_ = collapsed_caller_tbl_.get(callee_, [])
                                        for (d_, _) in d_lv_list_:
                                            nid_ = d_['id']
                                            try:
                                                nid_callee_lv_tbl[nid_].append((callee_, lv_))
                                            except KeyError:
                                                nid_callee_lv_tbl[nid_] = [(callee_, lv_)]
                                iter_d(chk, callee_d)

                            max_lv = 0
                            selected = None
                            for (d, lv) in d_lv_list:
                                if lv > max_lv:
                                    max_lv = lv
                                    selected = d
                                self.debug('    nid=%s lv=%d' % (d['id'], lv))

                            selected_id = selected['id']
                            self.debug('    -> selected %s' % selected_id)

                            copied_dl = []

                            try:
                                base = '%s%s' % (selected_id, NID_SEP)

                                def conv_id(i):
                                    return base+i

                                def hook(x):
                                    xid = x['id']
                                    for (c, lv) in nid_callee_lv_tbl.get(xid, []):
                                        lv_ = max_lv + lv + 1
                                        try:
                                            l = new_collapsed_caller_tbl[c]
                                            if not any([x_['id'] == xid and lv_ == lv__ for (x_, lv__) in l]):
                                                l.append((x, lv_))
                                        except KeyError:
                                            new_collapsed_caller_tbl[c] = [(x, lv_)]
                                    x['id'] = conv_id(xid)

                                for callee_d in callee_dl:
                                    info = {'count':0}
                                    copied = copy_dict(callee_d, hook=hook, info=info)
                                    copied_dl.append(copied)
                                    self.debug('%d nodes copied' % info['count'])

                                selected['children'] = copied_dl
                                callees_tbl[callee] = [d['id'] for d in copied_dl]
                                self.debug('callees_tbl: %s -> [%s]' % (callee, ','.join(callees_tbl[callee])))
                            except Exception, e:
                                self.warning(str(e))

                    if new_collapsed_caller_tbl:
                        collapsed_caller_tbl = new_collapsed_caller_tbl
                        self.debug('new_collapsed_caller_tbl:')
                    else:
                        collapsed_caller_tbl = {}
                    for (callee, d_lv_list) in new_collapsed_caller_tbl.iteritems():
                        self.debug('callee=%s' % callee)
                        for (d, lv) in d_lv_list:
                            self.debug('%s (lv=%d)' % (d['id'], lv))

            if metrics_dir:
                if ensure_dir(metrics_dir):

                    metrics_file_name = self.gen_metrics_file_name(lver)
                    metrics_path = os.path.join(metrics_dir, metrics_file_name)

                    self.message('dumping metrics into "%s"...' % metrics_path)
                    self.message('%d rows found' % len(csv_rows))

                    try:
                        with open(metrics_path, 'w') as metricsf:
                            csv_writer = csv.writer(metricsf)
                            csv_writer.writerow(METRICS_ROW_HEADER)
                            nid_i = METRICS_ROW_HEADER.index('nid')
                            for row in csv_rows:
                                root_nid = row[nid_i]
                                while True:
                                    try:
                                        root_nid = parent_tbl[root_nid]
                                    except KeyError:
                                        break

                                if not nid_tbl.has_key(root_nid):
                                    print row

                                row.append(nid_tbl[root_nid])

                                csv_writer.writerow(row)

                    except Exception, e:
                        self.warning(str(e))


            # clean up relevant_node_tbl
            p_to_be_del = []
            for (p, ltbl) in relevant_node_tbl.iteritems():
                ln_to_be_del = []
                for (ln, nids) in ltbl.iteritems():
                    if len(nids) < 2:
                        ln_to_be_del.append(ln)
                for ln in ln_to_be_del:
                    del ltbl[ln]
                if len(ltbl) == 0:
                    p_to_be_del.append(p)
            for p in p_to_be_del:
                del relevant_node_tbl[p]

            #

            json_ds.sort(key=lambda x: x['text'])

            lver_dir = os.path.join(outline_v_dir, lver)

            path_tbl = {} # path -> fid

            idx_range_tbl = {} # fidi -> (lmi * idx)

            if ensure_dir(lver_dir):
                try:
                    with open(os.path.join(lver_dir, 'path_list.json'), 'w') as plf:
                        plf.write(json.dumps(path_list))

                except Exception, e:
                    self.warning(str(e))

                try:
                    with open(os.path.join(lver_dir, 'fid_list.json'), 'w') as flf:
                        flf.write(json.dumps(fid_list))

                except Exception, e:
                    self.warning(str(e))

                idx_gen = IndexGenerator(init=1)

                for json_d in json_ds:
                    json_d['node_tbl'] = relevant_node_tbl
                    json_d['state'] = { 'opened' : True }

                    callees_tbl = None

                    for d in json_d['children']:
                        try:
                            r = d_tbl[d['id']]
                            self.debug('r=%s' % r)
                            callees_tbl = root_callees_tbl[r]
                            if callees_tbl:
                                self.debug('callees_tbl found')
                                json_d['callees_tbl'] = callees_tbl
                        except KeyError:
                            pass

                    fidi = json_d['fid']
                    loci = json_d['loc']

                    fid = fid_list[fidi]
                    loc = path_list[loci]

                    path_tbl[loci] = fidi

                    data_file_name = self.gen_data_file_name(fid)

                    lver_loc_dir = os.path.join(lver_dir, loc)

                    if ensure_dir(lver_loc_dir):

                        data_path = os.path.join(lver_loc_dir, data_file_name)

                        if dp.debug_flag:
                            self.debug('indexing for "%s"...' % data_path)
                            st = time()

                        index(idx_gen, json_d, callees_tbl)

                        idx = json_d.get('idx', None)
                        lmi = json_d.get('lmi', None)
                        if idx and lmi:
                            idx_range_tbl[fidi] = (lmi, idx, loci)

                        if dp.debug_flag:
                            self.debug('done. (%0.3f sec)' % (time() - st))

                        self.message('dumping object into "%s"...' % data_path)

                        try:
                            with open(data_path, 'wb') as f:
                                msgpack.pack(json_d, f)

                        except Exception, e:
                            self.warning(str(e))
                            continue

            #

            is_gitrev = self._conf.is_vkind_gitrev()
            vid = get_localname(ver) if is_gitrev else self.get_ver_dir_name(ver)

            vitbl = {
                'path_tbl': path_tbl,
                'vid'     : vid,
            }
            try:
                with open(os.path.join(lver_dir, 'index.json'), 'w') as vif:
                    vif.write(json.dumps(vitbl))

            except Exception, e:
                self.warning(str(e))

            try:
                with open(os.path.join(lver_dir, 'idx_range.json'), 'w') as irf:
                    irf.write(json.dumps(idx_range_tbl))

            except Exception, e:
                self.warning(str(e))

        #

        pitbl = {
            'hash_algo' : self._hash_algo,
            'ver_kind'  : self._conf.vkind,
        }
        try:
            with open(os.path.join(outline_dir, 'index.json'), 'w') as pif:
                pif.write(json.dumps(pitbl))

        except Exception, e:
            self.warning(str(e))


def test(proj):
    lang = 'fortran'
    #proj = 'MG'

    ol = Outline(proj)

    tree = ol.get_tree(lang)

    root_tbl = {} # ver -> loc -> root (contains loop)

    def f(lv, k):
        if 'do-construct' in k.cats:
            raise Exit

    count = 0

    for root in tree['roots']:
        try:
            ol.iter_tree(root, f)
        except Exit:
            count += 1

            loc_tbl = tbl_get_dict(root_tbl, root.ver)

            roots = tbl_get_list(loc_tbl, root.loc)

            roots.append(root)

    dp.message('%d top constructs (that contain loops) found' % count)


    def dump(lv, k):
        print('%s%s' % ('  '*lv, k))

    for ver in root_tbl.keys():
        lver = get_lver(ver)

        # if lver != 'base':
        #     continue

        loc_tbl = root_tbl[ver]
        for loc in loc_tbl.keys():
            print('*** ver=%s loc=%s' % (lver, loc))
            for root in loc_tbl[loc]:
                ol.iter_tree(root, dump)


def test2(proj):
    lang = 'fortran'

    ol = Outline(proj)

    tree = ol.get_tree(lang)

    node_tbl = tree['node_tbl']

    sub = None

    for (k, node) in node_tbl.iteritems():
        if node.loc == 'ic/grafic.f90':
            if 'subroutine-external-subprogram' in node.cats:
                sub = node

    if sub:
        print(len(sub.get_children()))
        for c in sub.get_children():
            print('%s %s' % (c, c != sub))



def main():
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

    parser = ArgumentParser(description='outline loops and get source code metrics for them',
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                        help='enable debug printing')

    parser.add_argument('--method', dest='method', default='odbc',
                        metavar='METHOD', type=str,
                        help='execute query via METHOD (odbc|http)')

    parser.add_argument('-c', '--commits', dest='commits', default=['HEAD'], nargs='+',
                        metavar='COMMIT', type=str, help='analyze COMMIT')

    parser.add_argument('-g', '--git-repo-base', dest='gitrepo', metavar='DIR', type=str,
                        default=GIT_REPO_BASE, help='location of git repositories')

    parser.add_argument('-p', '--proj-dir', dest='proj_dir', metavar='DIR', type=str,
                        default=PROJECTS_DIR, help='location of projects')

    parser.add_argument('--ver', dest='ver', metavar='VER', type=str,
                        default='unknown', help='version')

    parser.add_argument('--simple-layout', dest='simple_layout',
                        action='store_true', help='assumes simple directory layout')

    parser.add_argument('-a', '--all-roots', dest='all_roots', action='store_true',
                        help='allow subprograms to be root nodes in addition to main programs')

    parser.add_argument('-o', '--outdir', dest='outdir', default='.',
                        metavar='DIR', type=str, help='dump data into DIR')

    parser.add_argument('-i', '--index', dest='index', metavar='PATH', type=str,
                        default=None, help='index file')

    parser.add_argument('-s', '--doc-src', dest='docsrc', metavar='DIR', type=str,
                        default=None, help='document source for topic search')

    parser.add_argument('-m', '--model', dest='model', metavar='MODEL', type=str,
                        default='lsi', help='topic model (lda|lsi|rp)')

    parser.add_argument('-t', '--ntopics', dest='ntopics', metavar='N', type=int,
                        default=32, help='number of topics')

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
        #test(proj)
        ol = Outline(proj,
                     commits=args.commits,
                     method=args.method,
                     gitrepo=args.gitrepo,
                     proj_dir=args.proj_dir,
                     ver=args.ver,
                     simple_layout=args.simple_layout,
        )

        for lang in QUERY_TBL.keys():
            ol.gen_data(lang, args.outdir, omitted=set(OMITTED), all_roots=args.all_roots)

            if args.index:
                dp.message('generating topic data...')
                ol.gen_topic(lang, args.outdir,
                             docsrc=args.docsrc,
                             index=args.index,
                             model=args.model,
                             ntopics=args.ntopics)


if __name__ == '__main__':
    main()
