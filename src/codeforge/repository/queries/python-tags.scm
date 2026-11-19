; SPDX-License-Identifier: MIT
; Copyright (c) 2016 Max Brunsfeld
;
; Derived from tree-sitter-python 0.25.0, queries/tags.scm
; https://github.com/tree-sitter/tree-sitter-python (MIT; full text in LICENSE-tree-sitter-python).
;
; Modifications for CodeForge:
; - Each `@name` capture is renamed to `@name.definition.<kind>` or `@name.reference.<kind>`
;   (the naming scheme Aider's repo map uses), so the flat dict returned by
;   QueryCursor.captures() carries the tag kind without needing matches().
; Verified to compile and run with tree-sitter 0.26.1 + tree-sitter-python 0.25.0.

(module (expression_statement (assignment left: (identifier) @name.definition.constant) @definition.constant))

(class_definition
  name: (identifier) @name.definition.class) @definition.class

(function_definition
  name: (identifier) @name.definition.function) @definition.function

(call
  function: [
      (identifier) @name.reference.call
      (attribute
        attribute: (identifier) @name.reference.call)
  ]) @reference.call
