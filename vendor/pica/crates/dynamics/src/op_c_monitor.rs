//! Default-off observational monitor. All source arguments are immutable.
//! No random draws, setters, proposals, or source-state mutations occur here.
use crate::state::AugmentedState;
use rand_chacha::ChaCha8Rng;
use serde_json::{json, Value};
use std::{fs::File,io::{BufWriter,Write},path::Path,sync::{Mutex,OnceLock}};
struct Monitor { public:BufWriter<File>, audit:BufWriter<File>, before:Value, dispatch:Value, action:String, refresh:Vec<String>, initialized:bool }
static MONITOR:OnceLock<Mutex<Monitor>>=OnceLock::new();
pub fn enable(dir:&Path) {
 let open=|name| BufWriter::new(File::options().write(true).create_new(true).open(dir.join(name)).expect("write-once monitor file"));
 let m=Monitor{public:open("controller.public.jsonl"),audit:open("controller.audit.jsonl"),before:Value::Null,dispatch:Value::Null,action:String::new(),refresh:vec![],initialized:false};
 assert!(MONITOR.set(Mutex::new(m)).is_ok(),"monitor already configured");
}
fn stored(v:Value)->Value { match v {
 Value::Number(ref n) if n.is_f64()=>Value::String(format!("f64:{:016x}",n.as_f64().unwrap().to_bits())),
 Value::Array(a)=>Value::Array(a.into_iter().map(stored).collect()),
 Value::Object(o)=>Value::Object(o.into_iter().map(|(k,v)|(k,stored(v))).collect()),
 _=>v
} }
fn state(s:&AugmentedState)->Value {stored(serde_json::to_value(s).unwrap())}
fn rng(r:&ChaCha8Rng)->Value {json!({"seed":r.get_seed(),"stream":r.get_stream(),"word_position":r.get_word_pos().to_string()})}
fn write(f:&mut BufWriter<File>,v:&Value){serde_json::to_writer(&mut *f,v).unwrap();f.write_all(b"\n").unwrap();}
// Replaced top-level fields suffice to recover the complete source checkpoint exactly.
fn delta(a:&Value,b:&Value)->Value { let mut o=serde_json::Map::new();for(k,v)in b.as_object().unwrap(){if a.get(k)!=Some(v){o.insert(k.clone(),v.clone());}}Value::Object(o) }
pub fn canonical_partition(p:&Value)->Value { if p.is_null(){return Value::Null} let mut seen=Vec::new();Value::Array(p.as_array().unwrap().iter().map(|x|{let j=match seen.iter().position(|v|v==x){Some(j)=>j,None=>{seen.push(x.clone());seen.len()-1}};json!(j)}).collect()) }
fn public_state(v:&Value)->Value {json!({"step":v["step"],"phase":v["phase"],"budget_bits":v["budget"],"partition":canonical_partition(&v["pica_state"]["spectral_partition"])})}
pub fn before(s:&AugmentedState,r:&ChaCha8Rng){if let Some(lock)=MONITOR.get(){let mut m=lock.lock().unwrap();let v=state(s);if !m.initialized{write(&mut m.audit,&json!({"kind":"initial","state":v,"rng":rng(r)}));write(&mut m.public,&json!({"kind":"initial","state":public_state(&v)}));m.initialized=true;}m.before=v;m.refresh.clear();}}
pub fn refresh(kind:&str){if let Some(lock)=MONITOR.get(){lock.lock().unwrap().refresh.push(kind.to_string());}}
pub fn dispatch(s:&AugmentedState,action:&str){if let Some(lock)=MONITOR.get(){let mut m=lock.lock().unwrap();m.dispatch=state(s);m.action=action.to_string();}}
pub fn after(s:&AugmentedState,r:&ChaCha8Rng){if let Some(lock)=MONITOR.get(){let mut m=lock.lock().unwrap();let v=state(s);let mut mods=Vec::new();
 for key in ["base_kernel","effective_kernel","gate_mask"] {
 // MarkovKernel serializes as an object with transition matrix `kernel`.
 let a=if key=="gate_mask"{&m.dispatch[key]}else{&m.dispatch[key]["kernel"]};
 let b=if key=="gate_mask"{&v[key]}else{&v[key]["kernel"]};
 if let(Some(aa),Some(bb))=(a.as_array(),b.as_array()){for(i,(row0,row1))in aa.iter().zip(bb).enumerate(){for(j,(x,y))in row0.as_array().unwrap().iter().zip(row1.as_array().unwrap()).enumerate(){if x!=y{mods.push(json!({"register":key,"row":i,"column":j}));}}}}
 }
 let outcome=|prefix:&str| {let acc=format!("{}_accepted",prefix);let rej=format!("{}_rejected",prefix);if v[&acc]!=m.dispatch[&acc]{"accepted"}else if v[&rej]!=m.dispatch[&rej]{"rejected"}else{"not_applicable"}};
 let pubrow=json!({"kind":"step","before":public_state(&m.before),"dispatch":public_state(&m.dispatch),"after":public_state(&v),"refresh":m.refresh,"partition_changed":canonical_partition(&m.before["pica_state"]["spectral_partition"])!=canonical_partition(&v["pica_state"]["spectral_partition"]),"primitive":m.action,"p1":outcome("p1"),"p2":outcome("p2"),"modifications":mods});
 let auditrow=json!({"kind":"step","step":s.step,"dispatch_delta":delta(&m.before,&m.dispatch),"successor_delta":delta(&m.dispatch,&v),"rng":rng(r)});
 write(&mut m.public,&pubrow);write(&mut m.audit,&auditrow);
 // Flush per step so an incomplete monitor cannot masquerade as a complete trace.
 m.public.flush().unwrap();m.audit.flush().unwrap();
}}
#[cfg(test)] mod tests {use super::*;#[test] fn canonical_names(){assert_eq!(canonical_partition(&json!([7,7,2,9,2])),json!([0,0,1,2,1]));}#[test] fn default_off(){assert!(MONITOR.get().is_none());refresh("no output");}#[test] fn exact_float_encoding(){assert_eq!(stored(json!(1.0)),json!("f64:3ff0000000000000"));}}
