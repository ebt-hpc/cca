# CCA/EBT

For improving the performance of an application, we have to examine
the application's source code.
CCA/EBT extracts the syntactic/semantic structures from the source
code written in Fortran, and then provides outline views of the
loop-nests and the call trees decorated with source code metrics.


## Usage

A docker image of CCA/EBT is available from a Docker Hub
[repository](https://hub.docker.com/r/ebtxhpc/cca/).
You can try it by way of a
[helper script](https://raw.githubusercontent.com/ebt-hpc/docker-cca/master/ebt.py),
which requires [Docker](https://www.docker.com/) and [Python (2.7)](https://www.python.org/).
When you install Docker, you should follow the instructions provided for various platforms:
[Mac (OSX Yosemite 10.10.3 or above)](https://docs.docker.com/docker-for-mac/install/),
[Windows (requires Windows 10 Professional or Enterprise 64-bit)](https://docs.docker.com/docker-for-windows/install/),
[Ubuntu](https://docs.docker.com/engine/installation/linux/docker-ce/ubuntu/),
[Debian](https://docs.docker.com/engine/installation/linux/docker-ce/debian/),
[CentOS](https://docs.docker.com/engine/installation/linux/docker-ce/centos/), and
[Fedora](https://docs.docker.com/engine/installation/linux/docker-ce/fedora/).


### Exapmles

We assume that the helper script `ebt.py` is located in the current
working directory.

    $ ./ebt.py outline DIR
    
Outlines Fortran programs in `DIR`.
    
    $ ./ebt.py treeview start DIR
    
Starts tree view service on port 18000 (default). You can access the
viewer at [URL](http://localhost:18000/).
Note that at least a loop that contains floating-point operations and
array references should occur in the programs.
Otherwise, no programs will be shown in the viewer.

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
In particular, facts in N-Triples format are loaded into an RDF store
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

### References

1. Masatomo Hashimoto, Masaaki Terai, Toshiyuki Maeda, and Kazuo Minami. 2018. CCA/EBT: Code Comprehension Assistance Tool for Evidence-Based Performance Tuning. Poster to be presented at *International Conference on High Performance Computing in Asia-Pacific Region (HPC Asia 2018)*, P18.
1. Masatomo Hashimoto, Masaaki Terai, Toshiyuki Maeda, and Kazuo Minami. 2017. An Empirical Study of Computation-Intensive Loops for Identifying and Classifying Loop Kernels. In *Proc 8th ACM/SPEC International Conference on Performance Engineering (ICPE 2017)*, 361–372.
1. Masatomo Hashimoto, Masaaki Terai, Toshiyuki Maeda, and Kazuo Minami. 2015. Extracting Facts from Performance Tuning History of Scientific Applications for Predicting Effective Optimization Patterns. In *Proc 12th IEEE/ACM Working Conference on Mining Software Repositories (MSR 2015)*, 13–23.

## License

Apache License, Version 2.0
