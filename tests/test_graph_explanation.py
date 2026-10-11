"""Explanation projection invariants; synthetic graph facts, no LLM."""
from intelligence.engine import proof_graph

def test_full_role_requirements_are_retained_for_ui_gaps():
    required=['Python']+['skill'+str(i) for i in range(12)]
    graph=proof_graph({'skills':['Python'],'roles':[{'id':'role','label':'Role','skills':required}],'evidence':[]})
    role=next(node for node in graph['nodes'] if node['kind']=='role')
    assert len(role['required_skills'])==13
    assert len(graph['opportunities'][0]['missing_skills'])==13
    assert not graph['opportunities'][0]['transferable_skills']

def test_owner_can_manage_inactive_proof_without_using_it_in_routing():
    evidence=[{'id':'hidden','title':'Hidden fixture','skills':['Python'],'status':'executed','weight':.8,'hidden':True},
              {'id':'disputed','title':'Disputed fixture','skills':['SQL'],'status':'executed','weight':.8,'disputed':True},
              {'id':'declared','title':'Claim fixture','skills':['Git'],'status':'declared','weight':.8}]
    graph=proof_graph({'skills':['Python','SQL','Git'],'roles':[],'evidence':evidence})
    assert len(graph['evidence_inventory'])==3
    assert len(graph['evidence'])==1
    assert not any(node['id'] in ('e:hidden','e:disputed') for node in graph['nodes'])
    assert not any(edge['from'] in ('e:hidden','e:disputed') for edge in graph['edges'])
    assert next(node for node in graph['nodes'] if node['id']=='s:git')['strength']==0

def test_public_prefilter_does_not_reintroduce_private_inventory():
    # Native candidate_graph filters hidden/disputed before invoking the engine.
    graph=proof_graph({'skills':['Python'],'roles':[],'evidence':[{'id':'public','title':'Public fixture','skills':['Python'],'status':'executed','weight':.8}]})
    assert [item['id'] for item in graph['evidence_inventory']]==['public']
    assert graph['evidence_inventory']==graph['evidence']
