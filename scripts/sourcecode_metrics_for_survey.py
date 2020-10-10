#!/usr/bin/env python3

'''
  Source code metrics for C programs

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

import pprint

import pathsetup
import dp

from sparql import get_localname
import sparql
from factutils.entity import SourceCodeEntity
from ns import FB_NS, NS_TBL
from virtuoso import VIRTUOSO_PW, VIRTUOSO_PORT

FOP_TBL = { # number of FP operations (for SPARC64 VIIIfx)
    'nint'  : 2,
    'jnint' : 2,
    'cos'   : 29,
    'dcos'  : 31,
    'exp'   : 19,
    'dexp'  : 23,
    'log'   : 19,
    'alog'  : 19,
    'dlog'  : 23,
    'mod'   : 8,
    'amod'  : 8,
    'dmod'  : 8,
    'sign'  : 2,
    'dsign' : 2,
    'sin'   : 29,
    'dsin'  : 31,
    'sqrt'  : 11,
    'dsqrt' : 21,
    'tan'   : 58,
    'dtan'  : 64,
}
FOP_TBL_DBL_EXTRA = {
    'cos'  : 2,
    'exp'  : 4,
    'log'  : 4,
    'sin'  : 2,
    'sqrt' : 10,
    'tan'  : 6,
}
FOP_TBL_VA = {
    'max'   : lambda n: n-1,
    'amax1' : lambda n: n-1,
    'dmax1' : lambda n: n-1,
    'min'   : lambda n: n-1,
    'amin1' : lambda n: n-1,
    'dmin1' : lambda n: n-1,
}

LINES_OF_CODE        = 'lines_of_code'
MAX_LOOP_DEPTH       = 'max_loop_depth'
MAX_FUSIBLE_LOOPS    = 'max_fusible_loops'
MAX_MERGEABLE_ARRAYS = 'max_mergeable_arrays'
MAX_ARRAY_RANK       = 'max_array_rank'
MAX_LOOP_LEVEL       = 'max_loop_level'

N_BRANCHES   = 'branches'
N_STMTS      = 'stmts'
N_FP_OPS     = 'fp_ops'
N_OPS        = 'ops'
N_CALLS      = 'calls'

N_A_REFS     = ['array_refs0','array_refs1','array_refs2']
N_IND_A_REFS = ['indirect_array_refs0','indirect_array_refs1','indirect_array_refs2']
N_DBL_A_REFS = ['dbl_array_refs0','dbl_array_refs1','dbl_array_refs2']

BF = ['bf0','bf1','bf2']

META_KEYS = ['proj', 'ver', 'path', 'sub', 'lnum', 'digest']

abbrv_tbl = {
    LINES_OF_CODE        : 'LOC',
    MAX_LOOP_DEPTH       : 'LpD',
    MAX_FUSIBLE_LOOPS    : 'FLp',
    MAX_MERGEABLE_ARRAYS : 'MA',
    MAX_ARRAY_RANK       : 'ARk',
    MAX_LOOP_LEVEL       : 'LLv',

    N_BRANCHES   : 'Br',
    N_STMTS      : 'St',
    N_FP_OPS     : 'FOp',
    N_OPS        : 'Op',
    N_CALLS      : 'Ca',

    N_A_REFS[0]     : 'AR0',
    N_IND_A_REFS[0] : 'IAR0',
    N_DBL_A_REFS[0] : 'DAR0',

    N_A_REFS[1]     : 'AR1',
    N_IND_A_REFS[1] : 'IAR1',
    N_DBL_A_REFS[1] : 'DAR1',

    N_A_REFS[2]     : 'AR2',
    N_IND_A_REFS[2] : 'IAR2',
    N_DBL_A_REFS[2] : 'DAR2',

    BF[0] : 'BF0',
    BF[1] : 'BF1',
    BF[2] : 'BF2',
}

###

def count_aas(aas):
    c = 0
    for aa in aas:
        if aa.startswith(','):
            c += 2
        else:
            c += 1
    return c

def get_nfops(name, nargs, double=False):
    nfop = 1
    try:
        nfop = FOP_TBL_VA[name](nargs)
    except KeyError:
        nfop = FOP_TBL.get(name, 1)
        if double:
            nfop += FOP_TBL_DBL_EXTRA.get(name, 0)
    prec = 's'
    if double:
        prec = 'd'
    dp.debug('%s{%s}(%d) --> %d' % (name, prec, nargs, nfop))
    return nfop


def make_feature_tbl():
    v = { 'meta' : {'proj' : '',
                    'ver'  : '', 
                    'path' : '',
                    'sub'  : '',
                    'lnum' : '',
                },
          
          BF[0]                : 0.0,
          BF[1]                : 0.0,
          BF[2]                : 0.0,

          N_FP_OPS             : 0,
          N_OPS                : 0,

          N_A_REFS[0]          : 0,
          N_IND_A_REFS[0]      : 0,
          N_DBL_A_REFS[0]      : 0,
          N_A_REFS[1]          : 0,
          N_IND_A_REFS[1]      : 0,
          N_DBL_A_REFS[1]      : 0,
          N_A_REFS[2]          : 0,
          N_IND_A_REFS[2]      : 0,
          N_DBL_A_REFS[2]      : 0,

          N_BRANCHES           : 0,
          N_STMTS              : 0,
          N_CALLS              : 0,

          LINES_OF_CODE        : 0,

          MAX_LOOP_LEVEL       : 0,
          MAX_ARRAY_RANK       : 0,
          MAX_LOOP_DEPTH       : 0,
          MAX_FUSIBLE_LOOPS    : 0,
          MAX_MERGEABLE_ARRAYS : 0,
      }
    return v

def ent_to_str(uri_str):
    return uri_str.replace(NS_TBL['ent_ns'], '')

def ftbl_to_string(ftbl):
    meta_str = '%(proj)s:%(ver)s:%(path)s:%(sub)s:%(lnum)s' % ftbl['meta']
    cpy = ftbl.copy()
    cpy['meta'] = meta_str

    ks = ftbl.keys()
    ks.remove('meta')
    
    fmt = '%(meta)s ('

    fmt += ','.join(['%s:%%(%s)s' % (abbrv_tbl[k], k) for k in ks])

    fmt += ')'

    s = fmt % cpy

    return s

def ftbl_list_to_orange(ftbl_list, outfile):
    
    if not ftbl_list:
        return

    import Orange

    ks = ftbl_list[0].keys()
    ks.remove('meta')

    items = list(ks)

    features = [Orange.feature.Continuous(k) for k in items]
    domain = Orange.data.Domain(features, False)

    def add_meta(m):
        domain.add_meta(Orange.feature.Descriptor.new_meta_id(), Orange.feature.String(m))

    keys = META_KEYS

    for k in keys:
        add_meta(k)

    data = Orange.data.Table(domain)
    
    for ftbl in ftbl_list:
        vs = [ftbl[item] for item in items]
        inst = Orange.data.Instance(domain, vs)
        m = ftbl['meta']
        for k in keys:
            inst[k] = m[k]

        data.append(inst)
    
    try:
        data.save(outfile)
    except Exception as e:
        dp.error(str(e))


Q_PROJ_LIST = '''
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?g
WHERE {
GRAPH ?g {
  ?src a src:SourceTree .
}
}
''' % NS_TBL

Q_LOOP_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?child_loop ?loop_d ?child_loop_d
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?loop_d
    WHERE {

      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

    } GROUP BY ?ver ?loc ?loop ?loop_d
  }

  OPTIONAL {
    ?child_loop a cpp:IterationStatement ;
                src:treeDigest ?child_loop_d ;
                cpp:inIterationStatement ?loop .

    FILTER (?child_loop != ?loop)
  }

  OPTIONAL {
    ?loop cpp:inFunctionDefinition ?fd .
    ?fd a cpp:FunctionDefinition ;
        cpp:provides/(cpp:name|cpp:regexp) ?fn .
    FILTER NOT EXISTS {
      ?loop cpp:inFunctionDefinition ?fd0 .
      ?fd0 cpp:inFunctionDefinition ?fd .
      FILTER (?fd != ?fd0)
    }
  }

}
}
''' % NS_TBL

Q_LOOP_FD_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?loop ?callee ?callee_loc ?loop_d
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?tu ?loop ?callee ?loc ?loop_d
    WHERE {

      ?call a ?call_cat OPTION (INFERENCE NONE) ;
            cpp:inIterationStatement ?loop ;
            cpp:mayCall ?callee .

      FILTER (?call_cat IN (cpp:PostfixExpressionFunCall,
                            cpp:PostfixExpressionFunCallGuarded))

      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc .

    } GROUP BY ?tu ?loop ?callee ?loc ?loop_d
  }

  ?callee a cpp:FunctionDefinition ;
          cpp:inTranslationUnit/src:inFile ?callee_file .

  ?callee_file a src:File ;
               src:location ?callee_loc ;
               ver:version ?ver .

  FILTER EXISTS {
    ?tu ver:version ?ver .
  }

}
}
''' % NS_TBL

Q_FD_FD_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?callee ?callee_loc
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?fd ?callee
    WHERE {

      ?call a ?call_cat OPTION (INFERENCE NONE) ;
            cpp:inFunctionDefinition ?fd ;
            cpp:mayCall ?callee .

      FILTER (?call_cat IN (cpp:PostfixExpressionFunCall,
                            cpp:PostfixExpressionFunCallGuarded))

      ?fd a cpp:FunctionDefinition ;
          cpp:inTranslationUnit/src:inFile ?file .

      FILTER NOT EXISTS {
        ?call cpp:inFunctionDefinition ?fd0 .
        ?fd0  cpp:inFunctionDefinition ?fd .
        FILTER (?fd != ?fd0)
      }

      ?file a src:File ;
            src:location ?loc ;
            ver:version ?ver .

    } GROUP BY ?ver ?loc ?fd ?callee
  }

  ?callee a cpp:FunctionDefinition ;
          cpp:inTranslationUnit*/src:inFile ?callee_file .

  ?callee_file a src:File ;
               src:location ?callee_loc ;
               ver:version ?ver .

}
}
''' % NS_TBL

Q_ARRAYS_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fn ?loop ?aname ?rank ?dtor ?tyc ?loop_d
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?tu ?loop ?a ?aname ?loop_d ?aa ?acat
    WHERE {

      ?aa a cpp:PostfixExpressionSubscr ;
          src:child0* ?a ;
          cpp:inIterationStatement ?loop .

      FILTER NOT EXISTS {
        ?aa src:parent+ ?aa0 .
        ?aa0 a cpp:PostfixExpressionSubscr .
      }

      ?a a ?acat OPTION (INFERENCE NONE) ;
         cpp:name ?aname .

      FILTER NOT EXISTS {
        ?a0 src:parent+ ?a ;
            cpp:name [] .
      }

      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

    } GROUP BY ?tu ?loop ?a ?aname ?loop_d ?aa ?acat
  }

  ?tu a cpp:TranslationUnit ;
      src:inFile/src:location ?loc ;
      ver:version ?ver .

  {
    SELECT DISTINCT ?aa (COUNT(DISTINCT ?aa0) AS ?rank)
    WHERE {
      ?aa0 a cpp:PostfixExpressionSubscr ;
           src:parent* ?aa .
    } GROUP BY ?aa
  }

  {
    SELECT DISTINCT ?a ?dtor ?dcat ?tyc ?ty
    WHERE {

      ?a cpp:declarator ?dtor .

      ?dtor a ?dcat OPTION (INFERENCE NONE) ;
            cpp:type ?ty ;
            cpp:declarationTypeSpec ?tspec .

      ?tspec a ?tyc OPTION (INFERENCE NONE) .

    } GROUP BY ?a ?dtor ?dcat ?tyc ?ty
  }

  OPTIONAL {
    ?loop cpp:inFunctionDefinition ?fd .
    ?fd a cpp:FunctionDefinition ;
        cpp:provides/(cpp:name|cpp:regexp) ?fn .
    FILTER NOT EXISTS {
      ?loop cpp:inFunctionDefinition ?fd0 .
      ?fd0 cpp:inFunctionDefinition ?fd .
      FILTER (?fd != ?fd0)
    }
  }

}
}
''' % NS_TBL

Q_FFR_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?fref ?fname ?nargs ?h ?loop_d
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

    } GROUP BY ?ver ?loc ?loop ?loop_d
  }

  OPTIONAL {
    ?loop cpp:inFunctionDefinition ?fd .
    ?fd a cpp:FunctionDefinition ;
        cpp:provides/(cpp:name|cpp:regexp) ?fn .
    FILTER NOT EXISTS {
      ?loop cpp:inFunctionDefinition ?fd0 .
      ?sp0 cpp:inFunctionDefinition ?fd .
      FILTER (?fd != ?fd0)
    }
  }

  {
    SELECT DISTINCT ?loop ?fref ?h ?fname (COUNT(DISTINCT ?arg) AS ?nargs) ?p
    WHERE {

      ?call a ?call_cat OPTION (INFERENCE NONE) ;
            src:treeDigest ?h ;
            src:child0 ?fref ;
            src:child1 ?arg ;
            src:child1 ?farg ;
            cpp:inIterationStatement ?loop .

      FILTER (?call_cat IN (cpp:PostfixExpressionFunCall,
                            cpp:PostfixExpressionFunCallGuarded))

      ?fref cpp:requires/cpp:name ?fname .

      ?farg a ?facat OPTION (INFERENCE NONE) .

      FILTER (EXISTS { ?farg a cpp:FloatingLiteral } ||
              EXISTS {
                ?farg cpp:declarator ?dtor .
                ?dtor a ?dcat OPTION (INFERENCE NONE) ;
                      cpp:declarationTypeSpec ?tspec .
                ?tspec a ?tcat OPTION (INFERENCE NONE) .
                FILTER (?tcat IN (cpp:Double, cpp:Float))
              }
              )

    } GROUP BY ?loop ?fref ?h ?fname ?p
  }

}
}
''' % NS_TBL

Q_DFR_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?fname ?h ?loop_d
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

    } GROUP BY ?ver ?loc ?loop ?loop_d
  }

  OPTIONAL {
    ?loop cpp:inFunctionDefinition ?fd .
    ?fd a cpp:FunctionDefinition ;
        cpp:provides/(cpp:name|cpp:regexp) ?fn .
    FILTER NOT EXISTS {
      ?loop cpp:inFunctionDefinition ?fd0 .
      ?sp0 cpp:inFunctionDefinition ?fd .
      FILTER (?fd != ?fd0)
    }
  }

  {
    SELECT DISTINCT ?loop ?fref ?h ?fname (COUNT(DISTINCT ?arg) AS ?nargs) ?p
    WHERE {

      ?call a ?call_cat OPTION (INFERENCE NONE) ;
            src:treeDigest ?h ;
            src:child0 ?fref ;
            src:child1 ?arg ;
            src:child1 ?farg ;
            cpp:inIterationStatement ?loop .

      FILTER (?call_cat IN (cpp:PostfixExpressionFunCall,
                            cpp:PostfixExpressionFunCallGuarded))

      ?fref cpp:requires/cpp:name ?fname .

      ?farg a ?facat OPTION (INFERENCE NONE) .

      FILTER (EXISTS { ?farg a cpp:FloatingLiteral } ||
              EXISTS {
                ?farg cpp:declarator ?dtor .
                ?dtor a ?dcat OPTION (INFERENCE NONE) ;
                      cpp:declarationTypeSpec ?tspec .
                ?tspec a ?tcat OPTION (INFERENCE NONE) .
                FILTER (?tcat IN (cpp:Double))
              }
              )

    } GROUP BY ?loop ?fref ?h ?fname ?p
  }

}
}
''' % NS_TBL

Q_FOP_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?nfop ?loop_d
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

    } GROUP BY ?ver ?loc ?loop ?loop_d
  }

  OPTIONAL {
    ?loop cpp:inFunctionDefinition ?fd .
    ?fd a cpp:FunctionDefinition ;
        cpp:provides/(cpp:name|cpp:regexp) ?fn .
    FILTER NOT EXISTS {
      ?loop cpp:inFunctionDefinition ?fd0 .
      ?sp0 cpp:inFunctionDefinition ?fd .
      FILTER (?fd != ?fd0)
    }
  }

  OPTIONAL {
    SELECT DISTINCT ?loop (COUNT(DISTINCT ?h) AS ?nfop)
    WHERE {

      ?fop a ?fop_cat OPTION (INFERENCE NONE) ;
           src:treeDigest ?h ;
           cpp:inIterationStatement ?loop .

      FILTER (?fop_cat IN (cpp:MultiplicativeExpressionMult,
                           cpp:MultiplicativeExpressionDiv,
                           cpp:MultiplicativeExpressionMod,
                           cpp:AdditiveExpressionAdd,
                           cpp:AdditiveExpressionSubt
                           ))

      ?opr a cpp:Expression ;
           src:parent+ ?fop .

      FILTER (EXISTS {
        ?opr a cpp:FloatingLiteral .
      } || EXISTS {
        ?opr cpp:declarator/cpp:declarationTypeSpec ?tspec .
        ?tspec a ?tcat OPTION (INFERENCE NONE) .
        FILTER (?tcat IN (cpp:Double,cpp:Float))
      })

    } GROUP BY ?loop
  }

}
}
''' % NS_TBL

Q_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?vname ?loop_d ?nbr ?nes ?nop ?nc
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?fd ?fn ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

      OPTIONAL {
        ?loop cpp:inFunctionDefinition ?fd .
        ?fd a cpp:FunctionDefinition ;
            cpp:provides/(cpp:name|cpp:regexp) ?fn .
        FILTER NOT EXISTS {
          ?loop cpp:inFunctionDefinition ?fd0 .
          ?sp0 cpp:inFunctionDefinition ?fd .
          FILTER (?fd != ?fd0)
        }
      }

    } GROUP BY ?ver ?loc ?loop ?fd ?fn ?loop_d
  }

  OPTIONAL {
    SELECT DISTINCT ?loop (COUNT(DISTINCT ?h) AS ?nop)
    WHERE {
      ?op a cpp:Expression ;
          src:treeDigest ?h ;
          cpp:inIterationStatement ?loop .

    } GROUP BY ?loop
  }

  OPTIONAL {
    SELECT DISTINCT ?loop (COUNT(DISTINCT ?br) AS ?nbr)
    WHERE {
      ?br a cpp:SelectionStatement ;
          a ?br_cat OPTION (INFERENCE NONE) ;
          cpp:inIterationStatement ?loop .
    } GROUP BY ?loop
  }

  OPTIONAL {
    SELECT DISTINCT ?loop (COUNT(DISTINCT ?stmt) AS ?nes)
    WHERE {
      ?stmt a cpp:Statement ;
            a ?stmt_cat OPTION (INFERENCE NONE) ;
            cpp:inIterationStatement ?loop .
    } GROUP BY ?loop
  }

  OPTIONAL {
    SELECT DISTINCT ?loop (COUNT(DISTINCT ?call) AS ?nc)
    WHERE {
      ?call a ?call_cat OPTION (INFERENCE NONE) ;
            cpp:inIterationStatement ?loop .

      FILTER (?call_cat IN (cpp:PostfixExpressionFunCall,
                            cpp:PostfixExpressionFunCallGuarded))

    } GROUP by ?loop
  }

}
}
''' % NS_TBL


Q_AREF0_AA_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?loop_d ?sig
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?fd ?fn ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

      OPTIONAL {
        ?loop cpp:inFunctionDefinition ?fd .
        ?fd a cpp:FunctionDefinition ;
            cpp:provides/(cpp:name|cpp:regexp) ?fn .
        FILTER NOT EXISTS {
          ?loop cpp:inFunctionDefinition ?fd0 .
          ?sp0 cpp:inFunctionDefinition ?fd .
          FILTER (?fd != ?fd0)
        }
      }

    } GROUP BY ?ver ?loc ?loop ?fd ?fn ?loop_d
  }

  {
    SELECT DISTINCT ?loop ?sig
    WHERE {

      ?aa a cpp:PostfixExpressionSubscr ;
          src:child0 ?a ;
          cpp:arrayRefSig0 ?asig0 ;
          cpp:inIterationStatement ?loop .

      OPTIONAL {
        ?assign a cpp:AssignmentOperatorExpression ;
                src:child0 ?aa .
      }
      BIND(IF(BOUND(?assign), CONCAT(",", ?asig0), ?asig0) AS ?sig)

      FILTER EXISTS {
         ?a cpp:declarator/cpp:declarationTypeSpec ?tspec .
         ?tspec a cpp:NumericType .
      }

    } GROUP BY ?loop ?sig
  }

}
}
''' % NS_TBL

Q_AREF0_IAA_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?loop_d ?sig
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?fd ?fn ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

      OPTIONAL {
        ?loop cpp:inFunctionDefinition ?fd .
        ?fd a cpp:FunctionDefinition ;
            cpp:provides/(cpp:name|cpp:regexp) ?fn .
        FILTER NOT EXISTS {
          ?loop cpp:inFunctionDefinition ?fd0 .
          ?sp0 cpp:inFunctionDefinition ?fd .
          FILTER (?fd != ?fd0)
        }
      }

    } GROUP BY ?ver ?loc ?loop ?fd ?fn ?loop_d
  }

  {
    SELECT DISTINCT ?loop ?sig
    WHERE {

      ?aa a cpp:PostfixExpressionSubscr ;
          src:child0 ?a ;
          src:child1 ?idx ;
          cpp:arrayRefSig0 ?asig0 ;
          cpp:inIterationStatement ?loop .

      OPTIONAL {
        ?assign a cpp:AssignmentOperatorExpression ;
                src:child0 ?aa .
      }
      BIND(IF(BOUND(?assign), CONCAT(",", ?asig0), ?asig0) AS ?sig)

      FILTER EXISTS {
         ?a cpp:declarator/cpp:declarationTypeSpec ?tspec .
         ?tspec a cpp:NumericType .
      }

      FILTER (EXISTS {
        ?x a cpp:Expression ;
           src:children [] ;
           src:parent+ ?idx0 .

        ?aa0 a cpp:PostfixExpressionSubscr ;
             src:child1 ?idx0 ;
             src:parent+ ?aa .

        FILTER (?x != ?aa)
      } || EXISTS {
        ?x a cpp:Expression ;
           src:children [] ;
           src:parent+ ?idx .
      })

    } GROUP BY ?loop ?sig
  }

}
}
''' % NS_TBL

Q_AREF0_DAA_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?loop_d ?sig
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?fd ?fn ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

      OPTIONAL {
        ?loop cpp:inFunctionDefinition ?fd .
        ?fd a cpp:FunctionDefinition ;
            cpp:provides/(cpp:name|cpp:regexp) ?fn .
        FILTER NOT EXISTS {
          ?loop cpp:inFunctionDefinition ?fd0 .
          ?sp0 cpp:inFunctionDefinition ?fd .
          FILTER (?fd != ?fd0)
        }
      }

    } GROUP BY ?ver ?loc ?loop ?fd ?fn ?loop_d
  }

  {
    SELECT DISTINCT ?loop ?sig
    WHERE {

      ?aa a cpp:PostfixExpressionSubscr ;
          src:child0 ?a ;
          src:child1 ?idx ;
          cpp:arrayRefSig0 ?asig0 ;
          cpp:inIterationStatement ?loop .

      OPTIONAL {
        ?assign a cpp:AssignmentOperatorExpression ;
                src:child0 ?aa .
      }
      BIND(IF(BOUND(?assign), CONCAT(",", ?asig0), ?asig0) AS ?sig)

      FILTER EXISTS {
         ?a cpp:declarator/cpp:declarationTypeSpec ?tspec .
         ?tspec a cpp:Double .
      }

    } GROUP BY ?loop ?sig
  }

}
}
''' % NS_TBL

Q_AREF12_AA_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?loop_d ?sig
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?fd ?fn ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

      OPTIONAL {
        ?loop cpp:inFunctionDefinition ?fd .
        ?fd a cpp:FunctionDefinition ;
            cpp:provides/(cpp:name|cpp:regexp) ?fn .
        FILTER NOT EXISTS {
          ?loop cpp:inFunctionDefinition ?fd0 .
          ?sp0 cpp:inFunctionDefinition ?fd .
          FILTER (?fd != ?fd0)
        }
      }

    } GROUP BY ?ver ?loc ?loop ?fd ?fn ?loop_d
  }

  {
    SELECT DISTINCT ?loop ?sig
    WHERE {

      ?aa a cpp:PostfixExpressionSubscr ;
          src:child0 ?a ;
          src:child1 ?idx ;
          cpp:inIterationStatement ?loop .

      OPTIONAL {
        ?aa cpp:arrayRefSig%%(level)d ?asig .
      }
      OPTIONAL {
        ?assign a cpp:AssignmentOperatorExpression ;
                src:child0 ?aa .
      }
      BIND(COALESCE(?asig, "") AS ?sig0)
      BIND(IF(BOUND(?assign) && ?sig0 != "", CONCAT(",", ?sig0), ?sig0) AS ?sig)

      FILTER EXISTS {
         ?a cpp:declarator/cpp:declarationTypeSpec ?tspec .
         ?tspec a cpp:NumericType .
      }

    } GROUP BY ?loop ?sig
  }

}
}
''' % NS_TBL

Q_AREF12_IAA_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?loop_d ?sig
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?fd ?fn ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

      OPTIONAL {
        ?loop cpp:inFunctionDefinition ?fd .
        ?fd a cpp:FunctionDefinition ;
            cpp:provides/(cpp:name|cpp:regexp) ?fn .
        FILTER NOT EXISTS {
          ?loop cpp:inFunctionDefinition ?fd0 .
          ?sp0 cpp:inFunctionDefinition ?fd .
          FILTER (?fd != ?fd0)
        }
      }

    } GROUP BY ?ver ?loc ?loop ?fd ?fn ?loop_d
  }

  {
    SELECT DISTINCT ?loop ?sig
    WHERE {

      ?aa a cpp:PostfixExpressionSubscr ;
          src:child0 ?a ;
          src:child1 ?idx ;
          cpp:inIterationStatement ?loop .

      OPTIONAL {
        ?aa cpp:arrayRefSig%%(level)d ?asig .
      }
      OPTIONAL {
        ?assign a cpp:AssignmentOperatorExpression ;
                src:child0 ?aa .
      }
      BIND(COALESCE(?asig, "") AS ?sig0)
      BIND(IF(BOUND(?assign) && ?sig0 != "", CONCAT(",", ?sig0), ?sig0) AS ?sig)

      FILTER EXISTS {
         ?a cpp:declarator/cpp:declarationTypeSpec ?tspec .
         ?tspec a cpp:NumericType .
      }

      FILTER (EXISTS {
        ?x a cpp:Expression ;
           src:children [] ;
           src:parent+ ?idx0 .

        ?aa0 a cpp:PostfixExpressionSubscr ;
             src:child1 ?idx0 ;
             src:parent+ ?aa .

        FILTER (?x != ?aa)
      } || EXISTS {
        ?x a cpp:Expression ;
           src:children [] ;
           src:parent+ ?idx .
      })

    } GROUP BY ?loop ?sig
  }

}
}
''' % NS_TBL

Q_AREF12_DAA_IN_LOOP_C = '''DEFINE input:inference "ont.cpi"
PREFIX cpp: <%(cpp_ns)s>
PREFIX ver: <%(ver_ns)s>
PREFIX src: <%(src_ns)s>
SELECT DISTINCT ?ver ?loc ?fd ?fn ?loop ?loop_d ?sig
WHERE {
GRAPH <%%(proj)s> {

  {
    SELECT DISTINCT ?ver ?loc ?loop ?fd ?fn ?loop_d
    WHERE {
      ?loop a cpp:IterationStatement ;
            src:treeDigest ?loop_d ;
            cpp:inTranslationUnit ?tu .

      ?tu a cpp:TranslationUnit ;
          src:inFile/src:location ?loc ;
          ver:version ?ver .

      OPTIONAL {
        ?loop cpp:inFunctionDefinition ?fd .
        ?fd a cpp:FunctionDefinition ;
            cpp:provides/(cpp:name|cpp:regexp) ?fn .
        FILTER NOT EXISTS {
          ?loop cpp:inFunctionDefinition ?fd0 .
          ?sp0 cpp:inFunctionDefinition ?fd .
          FILTER (?fd != ?fd0)
        }
      }

    } GROUP BY ?ver ?loc ?loop ?fd ?fn ?loop_d
  }

  {
    SELECT DISTINCT ?loop ?sig
    WHERE {

      ?aa a cpp:PostfixExpressionSubscr ;
          src:child0 ?a ;
          src:child1 ?idx ;
          cpp:inIterationStatement ?loop .

      OPTIONAL {
        ?aa cpp:arrayRefSig%%(level)d ?asig .
      }
      OPTIONAL {
        ?assign a cpp:AssignmentOperatorExpression ;
                src:child0 ?aa .
      }
      BIND(COALESCE(?asig, "") AS ?sig0)
      BIND(IF(BOUND(?assign) && ?sig0 != "", CONCAT(",", ?sig0), ?sig0) AS ?sig)

      FILTER EXISTS {
         ?a cpp:declarator/cpp:declarationTypeSpec ?tspec .
         ?tspec a cpp:Double .
      }

    } GROUP BY ?loop ?sig
  }

}
}
''' % NS_TBL


QUERY_TBL = { 'cpp':
              { 
                  'loop_loop'      : Q_LOOP_LOOP_C,
                  'arrays'         : Q_ARRAYS_C,
                  'ffr_in_loop'    : Q_FFR_IN_LOOP_C,
                  'dfr_in_loop'    : Q_DFR_IN_LOOP_C,
                  'fop_in_loop'    : Q_FOP_IN_LOOP_C,
                  'in_loop'        : Q_IN_LOOP_C,

                  'aref0_in_loop'  : { 'aa' : Q_AREF0_AA_IN_LOOP_C,
                                       'iaa': Q_AREF0_IAA_IN_LOOP_C,
                                       'daa': Q_AREF0_DAA_IN_LOOP_C,
                                   },

                  'aref12_in_loop' : { 'aa' : Q_AREF12_AA_IN_LOOP_C,
                                       'iaa': Q_AREF12_IAA_IN_LOOP_C,
                                       'daa': Q_AREF12_DAA_IN_LOOP_C,
                                   },

                  'loop_fd'        : Q_LOOP_FD_C,
                  'fd_fd'          : Q_FD_FD_C,
              },
          }

N_LANGS = len(QUERY_TBL)

GITREV_PREFIX = NS_TBL['gitrev_ns']

def get_lver(uri):
    v = get_localname(uri)
    if uri.startswith(GITREV_PREFIX):
        v = v[0:7]
    return v


def get_proj_list(method='odbc'):
    driver = sparql.get_driver(method)

    proj_list = []

    for qvs, row in driver.query(Q_PROJ_LIST):
        g = row['g']
        proj_list.append(get_localname(g))

    return proj_list


class Ent:
    def __init__(self, ent, is_loop=False):
        self.ent = ent
        self.is_loop = is_loop

    def __hash__(self):
        return self.ent.__hash__()

    def __eq__(self, other):
        return self.ent == other.ent and self.is_loop == other.is_loop
        


class Metrics(dp.base):
    def __init__(self, proj_id, method='odbc',
                 pw=VIRTUOSO_PW, port=VIRTUOSO_PORT):

        self._proj_id = proj_id
        self._graph_uri = FB_NS + proj_id
        self._sparql = sparql.get_driver(method, pw=pw, port=port)

        self._tree_tbl = {} # lang -> tree

        self._result_tbl = {} # lang -> item name -> (ver * loc * lnum) -> value

        self._metadata_tbl = {} # (ver * loc * lnum) -> {'fn','digest'}

        self._ipp_tbl = {} # uri -> uri (inter-procedural parent tbl)

        self._ent_tbl = {} # uri -> is_loop

        self._loop_digest_tbl = {} # (ver * loc * fn * loop) -> digest set

        self._max_loop_level_tbl = {} # uri -> lv

    def get_loop_digest(self, key):
        digest = None
        ds = self._loop_digest_tbl.get(key, None)
        if ds:
            digest = ':'.join(sorted(list(ds)))
        return digest

    def set_loop_digest(self, key, d):
        try:
            s = self._loop_digest_tbl[key]
        except KeyError:
            s = set()
            self._loop_digest_tbl[key] = s
        s.add(d)

    def get_metadata(self, key):
        return self._metadata_tbl[key]

    def get_tree(self, lang):
        return self._tree_tbl[lang]

    def set_tree(self, lang, tree):
        self._tree_tbl[lang] = tree


    def get_item_tbl(self, lang, name):
        tbl = {}
        try:
            tbl = self._result_tbl[lang][name]
        except:
            pass
        return tbl

    def get_value(self, name, key):
        v = 0
        for lang in self._result_tbl.keys():
            try:
                v = self._result_tbl[lang][name][key]
                break
            except KeyError:
                pass

        return v

    def _get_value(self, lang, name, key):
        v = 0
        try:
            v = self._result_tbl[lang][name][key]
        except KeyError:
            pass
        return v

    def search(self, _key): # VER:PATH:LNUM

        key = tuple(_key.split(':'))

        self.message('key=(%s,%s,%s)' % key)

        ftbl_list = []

        for lang in self._result_tbl.keys():
            try:
                ftbl = self.find_ftbl(lang, key)
                ftbl_list.append(ftbl)
            except KeyError:
                pass

        return ftbl_list

    def dump(self):
        pp = pprint.PrettyPrinter(indent=2)
        pp.pprint(self._result_tbl)


    def find_ftbl(self, lang, key):
        md = self.get_metadata(key)
        fn = md['fn']
        digest = md['digest']

        (ver, path, lnum) = key

        ftbl = make_feature_tbl()

        ftbl['meta'] = {
            'proj'   : self._proj_id,
            'ver'    : ver,
            'path'   : path,
            'fn'     : fn,
            'lnum'   : str(lnum),
            'digest' : digest,
        }

        fop = self._get_value(lang, N_FP_OPS, key)

        if fop > 0:
            for lv in range(3):
                if BF[lv] in ftbl:
                    aa  = self._get_value(lang, N_A_REFS[lv], key)
                    daa = self._get_value(lang, N_DBL_A_REFS[lv], key)
                    saa = aa - daa
                    bf = float(saa * 4 + daa * 8) / float(fop)
                    ftbl[BF[lv]] = bf
            
        for item in ftbl.keys():
            try:
                ftbl[item] = self._result_tbl[lang][item][key]
            except KeyError:
                pass

        return ftbl
        

    def get_ftbl_list(self):
        keys_tbl = {} # lang -> keys
        for (lang, item_tbl) in self._result_tbl.items():
            try:
                keys = keys_tbl[lang]
            except KeyError:
                keys = set()
                keys_tbl[lang] = keys

            for (item, tbl) in item_tbl.items():
                for k in tbl.keys():
                    keys.add(k)

        ftbl_list = []

        for (lang, keys) in keys_tbl.items():
            for key in keys:
                ftbl = self.find_ftbl(lang, key)
                ftbl_list.append(ftbl)

        return ftbl_list


    def key_to_string(self, key):
        (ver, loc, fn, loop, vname) = key
        e = SourceCodeEntity(uri=loop)
        lnum = e.get_range().get_start_line()
        s = '%s:%s:%s:%s' % (ver, loc, fn, lnum)
        return s


    def set_metrics(self, lang, name, _key, value, add=False):
        (ver, loc, fn, loop, vname) = _key

        ent = SourceCodeEntity(uri=loop)
        lnum = ent.get_range().get_start_line()

        key = (ver, loc, str(lnum))
        key_str = '%s:%s:%s' % key

        self.debug('%s(%s): %s -> %s' % (self.key_to_string(_key), key_str, name, value))

        loop_d = self.get_loop_digest(_key)

        self._metadata_tbl[key] = {'fn':fn,'digest':loop_d}

        try:
            ntbl = self._result_tbl[lang]
        except KeyError:
            ntbl = {}
            self._result_tbl[lang] = ntbl

        try:
            tbl = ntbl[name]
        except KeyError:
            tbl = {}
            ntbl[name] = tbl

        if add:
            v = tbl.get(key, 0)
            tbl[key] = v + value
        else:
            tbl[key] = value


    def ipp_add(self, ent, parent, is_loop=False):
        try:
            s = self._ipp_tbl[ent]
        except KeyError:
            s = set()
            self._ipp_tbl[ent] = s

        self._ent_tbl[parent] = is_loop
        s.add(parent)


    def finalize_ipp(self):
        self.message('finalizing call graph...')
        for lang in QUERY_TBL.keys():
            query = QUERY_TBL[lang]['fd_fd'] % { 'proj' : self._graph_uri }

            for qvs, row in self._sparql.query(query):
                callee = row['callee']
                fd     = row['fd']
                self.ipp_add(callee, fd)

            query = QUERY_TBL[lang]['loop_fd'] % { 'proj' : self._graph_uri }

            for qvs, row in self._sparql.query(query):
                callee = row['callee']
                loop   = row['loop']
                self.ipp_add(callee, loop, is_loop=True)


    def build_tree(self, lang, f=None):
        query = QUERY_TBL[lang]['loop_loop'] % { 'proj' : self._graph_uri }

        children_tbl = {}
        parent_tbl = {}

        for qvs, row in self._sparql.query(query):
            ver   = row['ver']
            loc   = row['loc']
            fn    = row.get('fn', '')
            loop  = row['loop']
            loop_d = row['loop_d']
            vname = ''

            child_loop = row.get('child_loop', None)
            child_loop_d = row.get('child_loop_d', '')
            child_vname = ''

            lver = get_lver(ver)

            key = (lver, loc, fn, loop, vname)
            self.set_loop_digest(key, loop_d)

            if f:
                f(key, row)

            try:
                child_loops = children_tbl[key]
            except KeyError:
                child_loops = []
                children_tbl[key] = child_loops

            if child_loop:
                child_key = (lver, loc, fn, child_loop, child_vname)
                self.set_loop_digest(child_key, child_loop_d)

                if child_key not in child_loops:
                    child_loops.append(child_key)
                    parent_tbl[child_key] = key
                    self.ipp_add(child_loop, loop, is_loop=True)

        roots = []
        for k in children_tbl.keys():
            if k not in parent_tbl:
                roots.append(k)
                r = SourceCodeEntity(uri=self.get_loop_of_key(k)).get_range()
                lines = r.get_end_line() - r.get_start_line() + 1
                self.set_metrics(lang, LINES_OF_CODE, k, lines)

        self.message('%d top loops found' % len(roots))
                
        tree = {'children':children_tbl,'parent':parent_tbl,'roots':roots}

        self.set_tree(lang, tree)

        return tree


    def iter_tree(self, tree, root, f):
        children_tbl = tree['children']
        for child in children_tbl.get(root, []):
            if root != child:
                self.iter_tree(tree, child, f)
        f(root)

    def calc_loop_metrics(self):
        self.message('calculating loop metrics...')
        for lang in QUERY_TBL.keys():
            try:
                tree = self.build_tree(lang)
                children_tbl = tree['children']
                parent_tbl   = tree['parent']
                top_loops    = tree['roots']

                #
                
                def get_max_depth(depth, key):
                    children = filter(lambda c: c != key, children_tbl.get(key, []))
                    l = [depth]+[get_max_depth(depth+1, k) for k in children]
                    return max(l)


                for key in top_loops:

                    max_loop_depth = get_max_depth(1, key)

                    fusible_tbl = {}

                    def find_fusible_loops(key):
                        for (_, _, _, _, vn) in children_tbl.get(key, []):
                            try:
                                fusible_tbl[(key, vn)] += 1
                            except KeyError:
                                fusible_tbl[(key, vn)] = 1
                    
                    self.iter_tree(tree, key, find_fusible_loops)
                    
                    max_fusible_loops = 0
                    if fusible_tbl:
                        max_fusible_loops = max(fusible_tbl.values())

                    self.debug('key=%s' % (self.key_to_string(key)))
                    self.debug('max_loop_depth=%d max_fusible_loops=%d' % (max_loop_depth,
                                                                           max_fusible_loops,
                                                                       ))

                    self.set_metrics(lang, MAX_LOOP_DEPTH, key, max_loop_depth)
                    self.set_metrics(lang, MAX_FUSIBLE_LOOPS, key, max_fusible_loops)

            except KeyError:
                pass

        self.message('done.')


    def get_key(self, row):
        ver    = row['ver']
        loc    = row['loc']
        fn     = row.get('fn', '')
        loop   = row['loop']
        vname  = ''

        lver = get_lver(ver)
        key = (lver, loc, fn, loop, vname)
        return key

    def get_loop_of_key(self, key):
        (lver, loc, fn, loop, vname) = key
        return loop

    def calc_array_metrics(self):
        self.message('calculating array metrics...')

        for lang in QUERY_TBL.keys():
            try:
                query = QUERY_TBL[lang]['arrays'] % { 'proj' : self._graph_uri }

                tbl = {}

                for qvs, row in self._sparql.query(query):
                    key = self.get_key(row)

                    array = row['dtor']
                    tyc   = row['tyc']
                    rank  = int(row['rank'])
                    try:
                        arrays = tbl[key]
                    except KeyError:
                        arrays = []
                        tbl[key] = arrays

                    arrays.append((array, (tyc, rank)))


                def get(key):
                    arrays = tbl.get(key, [])
                    max_rank = 0
                    t = {}
                    for (a, spec) in arrays:
                        (tyc, rank) = spec
                        if rank > max_rank:
                            max_rank = rank
                        try:
                            t[spec] += 1
                        except KeyError:
                            t[spec] = 1

                    max_mergeable_arrays = 0
                    for spec in t.keys():
                        if t[spec] > max_mergeable_arrays:
                            max_mergeable_arrays = t[spec]

                    return {'max_rank':max_rank, 'max_mergeable_arrays':max_mergeable_arrays}


                tree = self.get_tree(lang)

                for key in tree['roots']:

                    data = {'max_rank':0, 'max_mergeable_arrays':0}

                    def f(k):
                        d = get(k)
                        if d['max_rank'] > data['max_rank']:
                            data['max_rank'] = d['max_rank']
                        if d['max_mergeable_arrays'] > data['max_mergeable_arrays']:
                            data['max_mergeable_arrays'] = d['max_mergeable_arrays']

                    self.iter_tree(tree, key, f)

                    self.debug('key=%s' % (self.key_to_string(key)))
                    self.debug('max_mergeable_arrays=%(max_mergeable_arrays)d max_rank=%(max_rank)d' % data)

                    self.set_metrics(lang, MAX_MERGEABLE_ARRAYS, key, data['max_mergeable_arrays'])
                    self.set_metrics(lang, MAX_ARRAY_RANK, key, data['max_rank'])

            except KeyError:
                pass

        self.message('done.')



    def calc_max_loop_level(self):
        self.message('calculating loop level...')
        for lang in QUERY_TBL.keys():
            tree = self.get_tree(lang)
            for key in tree['roots']:
                loop = self.get_loop_of_key(key)
                lv = self.get_max_loop_level(loop)
                self.set_metrics(lang, MAX_LOOP_LEVEL, key, lv)

    def get_max_loop_level(self, ent):
        lv = self._get_max_loop_level([], ent)
        return lv
            
    def _get_max_loop_level(self, traversed, ent):
        max_lv = 0
        try:
            max_lv = self._max_loop_level_tbl[ent]
        except KeyError:
            n = len(traversed)
            lvs = []
            indent = '  '*n
            self.debug('%s* %s ->' % (indent, ent_to_str(ent)))
            for p in self._ipp_tbl.get(ent, []):
                lv = 0
                is_loop = self._ent_tbl[p]

                if p not in traversed and p != ent:
                    if is_loop:
                        lv += 1
                    lv += self._get_max_loop_level([ent]+traversed, p)

                self.debug('%s  %s (%s) %d' % (indent, ent_to_str(p), is_loop, lv))

                lvs.append(lv)

            if lvs:
                max_lv = max(lvs)
            
            self._max_loop_level_tbl[ent] = max_lv

            self.debug('%s%d' % (indent, max_lv))

        return max_lv

    def calc_in_loop_metrics(self):
        self.message('calculating other in_loop metrics...')
        for lang in QUERY_TBL.keys():
            try:
                query = QUERY_TBL[lang]['in_loop'] % { 'proj' : self._graph_uri }

                def make_data():
                    return { 'nbr'  : 0,
                             'nes'  : 0,
                             'nop'  : 0,
                             'nc'   : 0,
                         }

                tbl = {}

                for qvs, row in self._sparql.query(query):

                    key = self.get_key(row)

                    data = make_data()
                    data['nbr']  = int(row['nbr'] or '0')
                    data['nes']  = int(row['nes'] or '0')
                    data['nop']  = int(row['nop'] or '0')
                    data['nc']   = int(row['nc'] or '0')

                    tbl[key] = data

                    fd = row['fd']
                    if fd:
                        self.ipp_add(row['loop'], fd)

                tree = self.get_tree(lang)

                for key in tree['roots']:
                    
                    data = make_data()
                    
                    def f(k):
                        d = tbl.get(k, None)
                        if d:
                            data['nbr']   += d['nbr']
                            data['nes']   += d['nes']
                            data['nop']   += d['nop']
                            data['nc']    += d['nc']

                    self.iter_tree(tree, key, f)

                    self.set_metrics(lang, N_BRANCHES,   key, data['nbr'])
                    self.set_metrics(lang, N_STMTS,      key, data['nes'])
                    self.set_metrics(lang, N_OPS,        key, data['nop'])
                    self.set_metrics(lang, N_CALLS,      key, data['nc'])

            except KeyError:
                raise
                pass

        self.message('done.')
    # end of calc_in_loop_metrics


    def calc_aref_in_loop_metrics(self, lv): # level: 0, 1, 2
        self.message('calculating other aref_in_loop metrics (lv=%d)...' % lv)

        for lang in QUERY_TBL.keys():
            try:
                if lv == 0:
                    qtbl = QUERY_TBL[lang]['aref0_in_loop']
                elif lv == 1 or lv == 2:
                    qtbl = QUERY_TBL[lang]['aref12_in_loop']
                else:
                    self.warning('illegal level: %d' % lv)
                    return

                tbl = {}

                kinds = ['aa','iaa','daa']

                def make_data():
                    d = {}
                    for k in kinds:
                        d[k] = set()
                    return d

                for kind in kinds:

                    query = qtbl[kind] % {'proj':self._graph_uri,'level':lv}
                    
                    for qvs, row in self._sparql.query(query):

                        key = self.get_key(row)

                        sig = row.get('sig')

                        if sig:
                            try:
                                data = tbl[key]
                            except KeyError:
                                data = make_data()
                                tbl[key] = data

                            data[kind].add(sig)

                        
                tree = self.get_tree(lang)

                for key in tree['roots']:
                    
                    data = make_data()
                    
                    def f(k):
                        d = tbl.get(k, None)
                        if d:
                            for kind in kinds:
                                data[kind] |= d.get(kind, set())

                    self.iter_tree(tree, key, f)

                    self.set_metrics(lang, N_A_REFS[lv],     key, count_aas(data['aa']))
                    self.set_metrics(lang, N_IND_A_REFS[lv], key, count_aas(data['iaa']))
                    self.set_metrics(lang, N_DBL_A_REFS[lv], key, count_aas(data['daa']))

            except KeyError:
                raise
                pass

        self.message('done.')
    # end of calc_aref_in_loop_metrics


    def calc_fop_in_loop_metrics(self):
        self.message('calculating fop metrics...')
        for lang in QUERY_TBL.keys():
            try:
                query = QUERY_TBL[lang]['fop_in_loop'] % { 'proj' : self._graph_uri }

                def make_data():
                    return { 
                             'nfop' : 0,
                         }

                tbl = {}

                for qvs, row in self._sparql.query(query):

                    key = self.get_key(row)

                    data = make_data()
                    data['nfop'] = int(row['nfop'] or '0')
                    
                    tbl[key] = data

                    fd = row['fd']
                    if fd:
                        self.ipp_add(row['loop'], fd)

                tree = self.get_tree(lang)

                for key in tree['roots']:

                    data = make_data()
                    
                    def f(k):
                        d = tbl.get(k, None)
                        if d:
                            data['nfop'] += d['nfop']

                    self.iter_tree(tree, key, f)

                    self.set_metrics(lang, N_FP_OPS, key, data['nfop'])
                    
            except KeyError:
                raise
                pass

        self.message('done.')
    # end of calc_fop_in_loop_metrics


    def calc_ffr_in_loop_metrics(self):
        self.message('calculating ffr metrics...')
        for lang in QUERY_TBL.keys():
            try:
                query = QUERY_TBL[lang]['ffr_in_loop'] % { 'proj' : self._graph_uri }

                tbl = {} # key -> hash -> fname * nargs * is_dbl
                
                for qvs, row in self._sparql.query(query):

                    key = self.get_key(row)
                
                    try:
                        fref_tbl = tbl[key] # hash -> fname * nargs * is_dbl
                    except KeyError:
                        fref_tbl = {}
                        tbl[key] = fref_tbl

                    h     = row['h']
                    fname = row['fname']
                    nargs = row['nargs']

                    fref_tbl[h] = (fname, nargs, False)

                    fd = row['fd']
                    if fd:
                        self.ipp_add(row['loop'], fd)

                #

                query = QUERY_TBL[lang]['dfr_in_loop'] % { 'proj' : self._graph_uri }
                for qvs, row in self._sparql.query(query):
                    key = self.get_key(row)
                    fref_tbl = tbl.get(key, None)
                    if fref_tbl:
                        h     = row['h']
                        fname = row['fname']
                        try:
                            (fn, na, b) = fref_tbl[h]
                            if fn == fname:
                                fref_tbl[h] = (fn, na, True)
                            else:
                                self.warning('function name mismatch (%s != %s)' % (fname, fn))
                        except KeyError:
                            self.warning('reference of %s not found (hash=%s)' % (fname, h))
                    
                #

                tree = self.get_tree(lang)

                def make_data():
                    return { 
                             'nfop' : 0,
                         }

                for key in tree['roots']:
                    
                    data = make_data()
                    
                    def f(k):
                        fref_tbl = tbl.get(k, None)
                        if fref_tbl:
                            for (h, (fn, na, dbl)) in fref_tbl.items():
                                data['nfop'] += get_nfops(fn, na, double=dbl)

                    self.iter_tree(tree, key, f)

                    self.set_metrics(lang, N_FP_OPS, key, data['nfop'], add=True)

            except KeyError:
                raise
                pass

        self.message('done.')
    # end of calc_ffr_in_loop_metrics


    def filter_results(self):
        self.message('filtering results...')

        to_be_removed = set()

        for (lang, item_tbl) in self._result_tbl.items():
            for item in (MAX_ARRAY_RANK, N_FP_OPS, N_A_REFS[0]):
                for (k, v) in item_tbl[item].items():
                    if v == 0:
                        to_be_removed.add(k)

        for (lang, item_tbl) in self._result_tbl.items():
            for (item, tbl) in item_tbl.items():
                for k in to_be_removed:
                    del tbl[k]
        

    def calc(self):
        self.message('calculating for "%s"...' % self._proj_id)
        self.calc_loop_metrics()
        self.calc_array_metrics()
        self.calc_fop_in_loop_metrics()
        self.calc_ffr_in_loop_metrics()

        for lv in range(3):
            self.calc_aref_in_loop_metrics(lv)

        self.calc_in_loop_metrics()
        self.finalize_ipp()
        self.calc_max_loop_level()
        self.filter_results()


if __name__ == '__main__':
    from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

    parser = ArgumentParser(description='get source code metrics')

    parser.add_argument('-d', '--debug', dest='debug', action='store_true', help='enable debug printing')

    parser.add_argument('-k', '--key', dest='key', default=None,
                        metavar='KEY', type=str, help='show metrics for KEY=VER:PATH:LNUM')

    parser.add_argument('-o', '--outfile', dest='outfile', default=None,
                        metavar='FILE', type=str, help='dump feature vector into FILE')

    parser.add_argument('-m', '--method', dest='method', default='odbc',
                        metavar='METHOD', type=str, help='execute query via METHOD (odbc|http)')

    parser.add_argument('proj_list', nargs='*', default=[], 
                        metavar='PROJ', type=str, help='project id (default: all projects)')

    args = parser.parse_args()

    dp.debug_flag = args.debug

    proj_list = []

    if args.key:
        l = args.key.split(':')
        if len(l) != 3:
            print('invalid key: %s' % args.key)
            exit(1)
        else:
            try:
                int(l[2])
            except:
                print('invalid key: %s' % args.key)
                exit(1)
                

    if args.proj_list:
        proj_list = args.proj_list
    else:
        proj_list = get_proj_list()


    ftbl_list = []

    for proj_id in proj_list:
        m = Metrics(proj_id, method=args.method)
        m.calc()

        if args.key:
            ftbl_list += m.search(args.key)
        else:
            ftbl_list += m.get_ftbl_list()

    if ftbl_list:
        if args.outfile:
            ftbl_list_to_orange(ftbl_list, args.outfile)
        else:
            for ftbl in sorted(ftbl_list,
                               key=lambda x: (x['meta']['ver'],
                                              x['meta']['fn'],
                                              x['meta']['lnum'])):
                print('%s' % ftbl_to_string(ftbl))

    else:
        print('not found')
