export type GraphNode={id:string;kind:string;label:string;strength?:number;source_id?:string;required_skills?:string[]};
export type GraphEdge={from:string;to:string;weight:number;relation:string};
export type ProofGraph={nodes:GraphNode[];edges:GraphEdge[];evidence?:any[];opportunities?:any[];neural?:any;version?:string};
export function graphSkills(graph:ProofGraph,roleId:string,query=''){
  const role=graph.nodes.find(node=>node.id===roleId);
  const opportunity=(graph.opportunities||[]).find(row=>'r:'+row.id===roleId);
  const requirements=role?.required_skills || (opportunity?[...opportunity.transferable_skills,...opportunity.missing_skills]:null);
  const nodes=new Map(graph.nodes.filter(node=>node.kind==='skill').map(node=>[node.label.toLowerCase(),node]));
  const labels=requirements?Array.from(new Set(requirements)):Array.from(nodes.keys());
  return labels.map(label=>nodes.get(label.toLowerCase())||{id:'s:'+label.toLowerCase(),label,kind:'skill',strength:0})
    .filter(node=>node.label.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a,b)=>Number((b.strength||0)>=.5)-Number((a.strength||0)>=.5)||a.label.localeCompare(b.label));
}
export function graphSources(graph:ProofGraph,skillId:string){
  const nodes=new Map(graph.nodes.map(node=>[node.id,node]));
  const evidence=new Map((graph.evidence||[]).map(row=>[row.id,row]));
  return graph.edges.filter(edge=>edge.to===skillId&&edge.relation==='supports')
    .map(edge=>({edge,node:nodes.get(edge.from),evidence:evidence.get(nodes.get(edge.from)?.source_id)}))
    .filter(row=>row.node?.kind==='evidence')
    .sort((a,b)=>b.edge.weight-a.edge.weight||a.edge.from.localeCompare(b.edge.from));
}
export function hasVerifiedTransfer(graph:ProofGraph,skillId:string,roleId:string){
  return graph.edges.some(edge=>edge.from===skillId&&edge.to===roleId&&edge.relation==='transfers_to'&&edge.weight>0);
}
