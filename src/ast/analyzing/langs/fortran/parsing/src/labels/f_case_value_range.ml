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
  | Value
  | Lower
  | Upper
  | LowerUpper

let to_string = function
  | Value      -> "Value"
  | Lower      -> "Lower"
  | Upper      -> "Upper"
  | LowerUpper -> "LowerUpper"

let to_simple_string = function
  | Value      -> "<value>"
  | Lower      -> "<lower>"
  | Upper      -> "<upper>"
  | LowerUpper -> "<lower-upper>"

let to_tag = function
  | Value      -> "Value", []
  | Lower      -> "Lower", []
  | Upper      -> "Upper", []
  | LowerUpper -> "LowerUpper", []
