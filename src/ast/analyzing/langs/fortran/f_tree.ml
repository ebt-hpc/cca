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
(* 
 * AST for Fortran
 *
 * fortran/tree.ml
 *
 *)

module L = F_label
module B = Binding
module P = Printer
module I = Pinfo
module H = Labels.HeaderFile

let sprintf = Printf.sprintf

let conv_loc = L.conv_loc

let set_loc nd loc = nd#data#set_loc (conv_loc loc)

module Tree = Sourcecode.Tree (L)
open Tree


let make_local_name mn un = 
  if mn = "" then
    un
  else
    String.concat "-" [mn; un]

let make_include_node options ast_nd =
  let f = Fname.strip (ast_nd#lloc#get_loc_of_level 1).Common.Loc.filename in
  let h = H.mkgenerated f in
  let nd = 
    mknode options (L.PpDirective (L.PpDirective.mk (L.PpDirective.Include h))) [] 
  in
  set_loc nd (ast_nd#lloc#get_loc_of_level 0);
  nd


let of_ast options ast =
  let utbl = Hashtbl.create 0 in

  let rec conv ?(label=None) ast_nd =
    let lab = 
      match label with
      | Some lab' -> lab'
      | None -> ast_nd#label
    in

    let is_incl nd =
      ast_nd#lloc#get_level = 0 && nd#lloc#get_level > 0
    in

    let rec conv_children = function
      | nd1::(nd2::rest as l) -> begin
          match nd1#label, nd2#label with
          | L.PartName n, L.SectionSubscriptList _ -> begin
              let x_opt0 = conv nd1 in
              let x_opt1 = conv ~label:(Some (L.SectionSubscriptList n)) nd2 in
              match x_opt0, x_opt1 with
              | Some x0, Some x1 -> x0 :: x1 :: (conv_children rest)
              | None, None -> conv_children rest
              | _ -> begin
                  Common.warning_msg "odd node sequence:\n%s\n%s"
                    nd1#to_string nd2#to_string;

                  conv_children rest
              end
          end
          | _ -> begin
              if is_incl nd1 then begin
                (make_include_node options nd1) :: (conv_children l)
              end
              else begin
                let x_opt = conv nd1 in
                match x_opt with
                | Some x -> x :: (conv_children l)
                | None -> conv_children l
              end
          end
      end
      | [nd] -> begin
          if is_incl nd then begin
            [make_include_node options nd]
          end
          else
            Xoption.to_list (conv nd)
      end
      | [] -> []
    in

    let children = conv_children ast_nd#children in

    if ast_nd#lloc#get_level > 0 && children = [] then
      None
    else begin

      let binding = ast_nd#binding in

      let info = ast_nd#info in

      let annot =
        let specs = ref [] in
        let lnames = ref [] in
        I.iter_external
          (fun (mn, un) ->
            lnames := (make_local_name mn un) :: !lnames
          ) info;
        begin
          match !lnames with
          | [] -> ()
          | _ -> specs := (L.Annotation.mkrequire !lnames) :: !specs
        end;
        begin
          match binding with
          | B.Def _ -> begin
              I.iter_name_spec
                (fun nspec ->
                  specs := (L.Annotation.mkspec nspec) :: !specs
                ) info
          end
          | _ -> ()
        end;
        begin
          try
            let n = L.get_external_subprogram_name ast_nd#label in
            specs := (L.Annotation.mkprovide [n]) :: !specs
          with
            Not_found -> ()
        end;
        L.Annotation.from_specs !specs
      in

      let nd = mknode options ~annot lab children in
      begin
        match binding with
        | B.None -> ()
        | B.Def(bid, use) -> begin
            let b =
              match use with
              | B.Unknown -> begin
                  try
                    B.make_used_def bid (Hashtbl.find utbl bid)
                  with
                    Not_found -> binding
              end
              | B.Used c -> binding
            in
            nd#data#set_binding b
        end
        | B.Use bid -> begin
            nd#data#set_binding binding;
            try
              let c = Hashtbl.find utbl bid in
              Hashtbl.replace utbl bid (c+1)
            with
              Not_found ->
                Hashtbl.add utbl bid 1
        end
      end;
      set_loc nd ast_nd#loc;
      Some nd
    end
  in (* let rec conv *)

  let root_node =
    let rt = ast#root in
    match conv rt with
    | Some rn -> rn
    | None -> begin
        try
          make_include_node options rt
        with
          Failure _ -> assert false
    end
  in
  let tree = new c options root_node true in
  tree#collapse;
  tree#set_total_LOC ast#lines_read;
  tree#set_ignored_regions (ast#comment_regions @ ast#ignored_regions);
  tree#set_misparsed_regions ast#missed_regions;
  tree
