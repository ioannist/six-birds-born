"""Historical symbolic witness, with explicit metric input instead of a loader.

Recovered from the executed CB algebraic witness. This is an original
implementation diagnostic, never the completed certificate or a gate on it.
The only adaptation is replacing the fixture/scratch loader with its exact s.
"""
import sympy as sp
Q=sp.Rational

def clean(M):return M.applyfunc(sp.simplify)
def eq(A,B):return clean(A-B)==sp.zeros(*A.shape)
def witness(s):
 s=Q(s.numerator,s.denominator);G=sp.diag(32,s);S=sp.diag(sp.sqrt(32),sp.sqrt(s));I=sp.eye(2)
 vectors=[sp.Matrix([1,0]),sp.Matrix([Q(1,2),sp.sqrt(3)/2]),sp.Matrix([Q(1,2),-sp.sqrt(3)/2])]
 # Orthonormal route: direct vector products. G route: metric-normalized vectors.
 ortho=[v*v.T for v in vectors];ortho+= [I-p for p in ortho]
 gvec=[clean(S.inv()*v) for v in vectors]
 frame=[clean(v*v.T*G) for v in gvec];frame += [I-p for p in frame]
 for p,r in zip(ortho,frame):
  assert eq(p*p,p) and sp.trace(p)==1 and p.det()==0
  assert eq(r*r,r) and sp.trace(r)==1 and eq(G*r,r.T*G)
  assert eq(clean(S*r*S.inv()),p)
  assert eq(clean(S.inv()*p*S),r)
 expected=[[1,Q(1,4),Q(1,4)],[Q(1,4),1,Q(1,4)],[Q(1,4),Q(1,4),1],[0,Q(3,4),Q(3,4)],[Q(3,4),0,Q(3,4)],[Q(3,4),Q(3,4),0]]
 table=[[sp.simplify(sp.trace(r*e)) for e in frame[:3]] for r in frame]
 direct=[[sp.simplify(sp.trace(r*e)) for e in ortho[:3]] for r in ortho]
 assert table==direct==expected
 mixtures=[[(i,Q(1,2)),(i+3,Q(1,2))] for i in range(3)]+[[(i,Q(1,3)) for i in range(3)],[(i,Q(1,3)) for i in range(3,6)]]
 for mixture in mixtures:
  for states in (frame,ortho):assert eq(sum((a*states[i] for i,a in mixture),sp.zeros(2)),I/2)
 return {'s':str(s),'G':[[str(v) for v in row] for row in G.tolist()],'ortho_states':[str(p) for p in ortho],'G_states':[str(p) for p in frame],'test_commands':['BIN(Pa)','BIN(Pb)','BIN(Pc)'],'YES_table':[[str(v) for v in row] for row in table],'mixtures':[[(i,str(a)) for i,a in m] for m in mixtures],'projectivity_trace_G_adjoint_conjugacy':True,'principal_roots_are_projectors':True,'domain':'external real densities/full effect interval; not asserted encoded/native','orthonormal_and_G_routes_independent':True,'measure_proof_parity_values':[0,2,4,6],'contradiction_value':3,'status':'PROVED UNDER ADOPTED MODEL'},ortho,frame,G

