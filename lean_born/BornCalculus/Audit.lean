import BornCalculus
import BornCalculus.Census.AuditFull
import Lean.Util.CollectAxioms

/- Fresh shared audit command. The Python driver supplies the recursive source
inventory and elaborates this command anew on every invocation. Imports never
stand in for a fresh audit. Generated compiler helpers and private constants
are traversed as dependencies, but do not inflate the source-declaration count.

The dependency cases below match Lean.Util.CollectAxioms. A worklist propagates
axiom sets over reverse edges to a fixed point, including mutual cycles. This
shares traversal across declarations without attributing earlier roots' axioms
to later roots. No axiom allowlist is applied here: the checked Python driver
rejects any unexpected axiom in the complete emitted result. -/
namespace BornCalculusAudit
open Lean Elab Command

private def dependencies (info : ConstantInfo) : Array Name :=
  match info with
  | .axiomInfo v => v.type.getUsedConstants
  | .defnInfo v => v.type.getUsedConstants ++ v.value.getUsedConstants
  | .thmInfo v => v.type.getUsedConstants ++ v.value.getUsedConstants
  | .opaqueInfo v => v.type.getUsedConstants ++ v.value.getUsedConstants
  | .quotInfo _ => #[]
  | .ctorInfo v => v.type.getUsedConstants
  | .recInfo v => v.type.getUsedConstants
  | .inductInfo v => v.type.getUsedConstants ++ v.ctors.toArray

private def auditGraph (env : Environment) (roots : Array Name) :
    Except String (NameMap NameSet × Nat × Nat) := do
  let mut pending := roots
  let mut seen : NameSet := {}
  let mut parents : NameMap (Array Name) := {}
  let mut sets : NameMap NameSet := {}
  let mut work : Array (Name × Name) := #[]
  let mut edges := 0
  while !pending.isEmpty do
    let name := pending.back!
    pending := pending.pop
    if seen.contains name then continue
    seen := seen.insert name
    let some info := env.checked.get.find? name
      | throw s!"unknown kernel declaration {name}"
    if let .axiomInfo _ := info then
      sets := sets.insert name ({name} : NameSet)
      work := work.push (name, name)
    for dep in dependencies info do
      parents := parents.insert dep ((parents.find? dep).getD #[] |>.push name)
      pending := pending.push dep
      edges := edges + 1
  while !work.isEmpty do
    let (name, ax) := work.back!
    work := work.pop
    for parent in (parents.find? name).getD #[] do
      let old := (sets.find? parent).getD {}
      unless old.contains ax do
        sets := sets.insert parent (old.insert ax)
        work := work.push (parent, ax)
  return (sets, seen.size, edges)

syntax "#audit_declarations " str : command

elab_rules : command
  | `(#audit_declarations $manifest:str) => do
    let start ← IO.monoMsNow
    let raw ← IO.FS.readFile manifest.getString
    let doc ← match Json.parse raw with
      | .ok value => pure value
      | .error e => throwError "invalid audit manifest: {e}"
    let rows ← match doc.getArr? with
      | .ok value => pure value
      | .error e => throwError "invalid audit manifest: {e}"
    let mut roots : Array Name := #[]
    let mut labels : Array String := #[]
    for row in rows do
      let label ← match row.getObjValAs? String "name" with
        | .ok value => pure value
        | .error e => throwError "invalid declaration name: {e}"
      let parts ← match row.getObjValAs? (Array String) "components" with
        | .ok value => pure value
        | .error e => throwError "invalid name components: {e}"
      let name := parts.foldl Name.str Name.anonymous
      let expected ← match row.getObjValAs? String "module" with
        | .ok value => pure value
        | .error e => throwError "invalid declaration module: {e}"
      let env ← getEnv
      let some owner := env.getModuleIdxFor? name |>.bind (env.header.modules[·]?)
        | throwError "declaration not imported from a compiled module: {label}"
      unless owner.module.toString == expected do
        throwError "wrong source module for {label}: expected {expected}, got {owner.module}"
      roots := roots.push name
      labels := labels.push label
    let (sets, nodes, edges) ← match auditGraph (← getEnv) roots with
      | .ok value => pure value
      | .error e => throwError "axiom audit failed: {e}"
    let mut result : List (String × Json) := []
    for i in [:roots.size] do
      let axs := (sets.find? roots[i]!).getD {}
      let mut values : Array Json := #[]
      for ax in axs do
        values := values.push (toJson ax.toString)
      result := (labels[i]!, Json.arr values) :: result
    let elapsed := (← IO.monoMsNow) - start
    let receipt := Json.mkObj [
      ("schema", toJson "born_axiom_dependencies_v2"),
      ("dependencies", Json.mkObj result.reverse),
      ("reachable_constants", toJson nodes),
      ("dependency_edges", toJson edges),
      ("traversal_ms", toJson elapsed)]
    IO.println s!"BORN_AXIOM_AUDIT_JSON {receipt.compress}"

end BornCalculusAudit
