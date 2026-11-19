; SPDX-License-Identifier: MIT
; Copyright (c) 2014 Max Brunsfeld
;
; Derived from tree-sitter-javascript 0.25.0, queries/tags.scm
; https://github.com/tree-sitter/tree-sitter-javascript (MIT; full text in LICENSE-tree-sitter-javascript).
;
; Modifications for CodeForge:
; - Each `@name` capture is renamed to `@name.definition.<kind>` or `@name.reference.<kind>`
;   (the naming scheme Aider's repo map uses), so the flat dict returned by
;   QueryCursor.captures() carries the tag kind without needing matches().
; - `new_expression` reference: capture only the class identifier (or the property of a
;   member expression) instead of `(_)`, so `new ns.Foo()` yields the name `Foo`, not `ns.Foo`.
; Notes:
; - `#strip!` and `#select-adjacent!` are not built into py-tree-sitter. They compile and are
;   ignored unless a custom predicate callable is passed to captures()/matches(). `@doc` is
;   therefore unprocessed; CodeForge ignores it.
; - `#not-eq?` and `#not-match?` are built in and are enforced by QueryCursor.captures() and
;   QueryCursor.matches() (checked: `require(...)` calls and `constructor` methods are dropped).
; Verified to compile and run with tree-sitter 0.26.1 + tree-sitter-javascript 0.25.0.

(
  (comment)* @doc
  .
  (method_definition
    name: (property_identifier) @name.definition.method) @definition.method
  (#not-eq? @name.definition.method "constructor")
  (#strip! @doc "^[\\s\\*/]+|^[\\s\\*/]$")
  (#select-adjacent! @doc @definition.method)
)

(
  (comment)* @doc
  .
  [
    (class
      name: (_) @name.definition.class)
    (class_declaration
      name: (_) @name.definition.class)
  ] @definition.class
  (#strip! @doc "^[\\s\\*/]+|^[\\s\\*/]$")
  (#select-adjacent! @doc @definition.class)
)

(
  (comment)* @doc
  .
  [
    (function_expression
      name: (identifier) @name.definition.function)
    (function_declaration
      name: (identifier) @name.definition.function)
    (generator_function
      name: (identifier) @name.definition.function)
    (generator_function_declaration
      name: (identifier) @name.definition.function)
  ] @definition.function
  (#strip! @doc "^[\\s\\*/]+|^[\\s\\*/]$")
  (#select-adjacent! @doc @definition.function)
)

(
  (comment)* @doc
  .
  (lexical_declaration
    (variable_declarator
      name: (identifier) @name.definition.function
      value: [(arrow_function) (function_expression)]) @definition.function)
  (#strip! @doc "^[\\s\\*/]+|^[\\s\\*/]$")
  (#select-adjacent! @doc @definition.function)
)

(
  (comment)* @doc
  .
  (variable_declaration
    (variable_declarator
      name: (identifier) @name.definition.function
      value: [(arrow_function) (function_expression)]) @definition.function)
  (#strip! @doc "^[\\s\\*/]+|^[\\s\\*/]$")
  (#select-adjacent! @doc @definition.function)
)

(assignment_expression
  left: [
    (identifier) @name.definition.function
    (member_expression
      property: (property_identifier) @name.definition.function)
  ]
  right: [(arrow_function) (function_expression)]
) @definition.function

(pair
  key: (property_identifier) @name.definition.function
  value: [(arrow_function) (function_expression)]) @definition.function

(
  (call_expression
    function: (identifier) @name.reference.call) @reference.call
  (#not-match? @name.reference.call "^(require)$")
)

(call_expression
  function: (member_expression
    property: (property_identifier) @name.reference.call)
  arguments: (_) @reference.call)

(new_expression
  constructor: [
    (identifier) @name.reference.class
    (member_expression
      property: (property_identifier) @name.reference.class)
  ]) @reference.class

(export_statement value: (assignment_expression left: (identifier) @name.definition.constant right: ([
 (number)
 (string)
 (identifier)
 (undefined)
 (null)
 (new_expression)
 (binary_expression)
 (call_expression)
]))) @definition.constant
