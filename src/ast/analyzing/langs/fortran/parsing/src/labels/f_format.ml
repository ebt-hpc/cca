(*
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
*)

(* Author: Masatomo Hashimoto <m.hashimoto@riken.jp> *)

open Label_common

type t =
  | Expr
  | Label of label
  | ListDirected

let to_string = function
  | Expr         -> "Expr"
  | Label lab    -> "Label:"^lab
  | ListDirected -> "ListDirected"

let to_simple_string = function
  | Expr         -> "<expr>"
  | Label lab    -> "<label:"^lab^">"
  | ListDirected -> "*"

let to_tag = function
  | Expr         -> "Expr", []
  | Label lab    -> "Label", [label_attr_name,lab]
  | ListDirected -> "ListDirected", []

let get_label = function
  | Label lab    -> lab
  | _ -> raise Not_found

let anonymize = function
  | Label lab    -> Label ""
  | l -> l