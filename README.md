# CCA/EBT

For improving the performance of an application, we have to comprehend
the application's source code. In order to facilitate comrehension of
source code written in Fortran, this utility analyzes its
syntactic/semantic structures and then provides outline views of
loop-nests and call trees decorated with source code metrics.


## Usage

A docker image of CCA/EBT is readily available from a Docker Hub
[repository](https://hub.docker.com/r/ebtxhpc/cca/).
You can try it easily by way of a
[helper script](https://raw.githubusercontent.com/ebt-hpc/docker-cca/master/ebt.py)
([Python](https://www.python.org/) and [Docker](https://www.docker.com/) required).

### Exapmles

We assume that the helper script `ebt.py` is located in the current
working directory.

    $ ./ebt.py outline DIR
    
Outlines Fortran programs in `DIR`.
    
    $ ./ebt.py treeview start DIR
    
Starts tree view service on port 18000 (default). You can access the
viewer at the [URL](http://localhost:18000/).

    $ ./ebt.py treeview stop DIR
    
Stops the viewer service.

    $ ./ebt.py opcount DIR
    
Counts the occurrences of operations and array references for each
Fortran program found in `DIR`.  The results are dumped into a directory
`DIR/_EBT_/`*YYYYMMDD*`T`*hhmmss* in JSON format.


## Contents

Based on [CCA](https://github.com/codinuum/cca/) framework, CCA/EBT
provides the following:

* a Fortran parser,
* scripts for topic analysis, outlining, and operation counting of Fortran programs,
* a web application that shows tree views of the outlines, and
* ontologies for Fortran entities.

The parser export resulting *facts* such as ASTs and
other syntactic information in [XML](https://www.w3.org/TR/xml11/) or
[N-Triples](https://www.w3.org/2001/sw/RDFCore/ntriples/).
In particular, facts in N-Triples format are loaded into an RDF store such as
[Virtuoso](https://github.com/openlink/virtuoso-opensource) to build a
*factbase*, or a database of facts.
Factbases are intended to be queried for code comprehension tasks.


## Building the parser(s)

### Requirements

* GNU make
* [OCaml](http://ocaml.org/) (>=4.02)
* [Findlib](http://projects.camlcity.org/projects/findlib.html)
* [Menhir](http://gallium.inria.fr/~fpottier/menhir/)
* [Ocamlnet](http://projects.camlcity.org/projects/ocamlnet.html) (>=4.1.0)
* [PXP](http://projects.camlcity.org/projects/pxp.html) (>=1.2.8)
* [Cryptokit](https://github.com/xavierleroy/cryptokit)
* [Camlzip](https://github.com/xavierleroy/camlzip)
* [OCaml CSV](https://github.com/Chris00/ocaml-csv)
* [Uuidm](http://erratique.ch/software/uuidm)
* [Volt](https://github.com/codinuum/volt)

### Compilation

The following create `ast/analyzing/bin/parsesrc.opt`.

    $ cd src
    $ make

It is called from a shell script `ast/analyzing/bin/parsesrc`.


## License

Apache License, Version 2.0