import pytest
from scripts import advanced_assurance as assurance
from intelligence import graph_neural as nn, market_models as mm

@pytest.mark.parametrize('seed',range(20))
def test_assignment_against_exhaustive_physical_person_oracle(seed):
    payload=assurance.market(seed)
    expected,_=assurance.exhaustive_assignment(payload)
    assert assurance.twins.allocation(payload)['total_utility']==pytest.approx(expected,abs=2e-6)

@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-0.001,1.001])
def test_graph_rejects_nonfinite_and_out_of_range_edge_weights(bad):
    graph=assurance.graph(17);graph['edges'][0]['weight']=bad
    with pytest.raises(ValueError):nn.tensors(graph)

@pytest.mark.parametrize('bad',[True,-1,10_000_001,2.5,'5',None])
def test_count_contract_rejects_unsafe_observations(bad):
    with pytest.raises(ValueError):mm.posterior({'accepted':bad})

def test_full_boolean_role_contract():
    assert assurance.role_contracts()['role_grade_gate_cases']==1200

def test_graph_metamorphic_identity_and_nonmutation():
    assert assurance.graph_contracts(cases=10)['input_mutations']==0

def test_independent_proper_scoring_oracles():
    assurance.score_contracts(cases=10)

def test_missing_joint_estimate_and_censoring_are_preserved():
    assurance.posterior_contracts(cases=30)

def test_small_sample_equivalence_and_activation_are_separate():
    assurance.equivalence_safety()

def test_response_signals_never_accuse_or_sanction():
    assurance.response_contracts()

def test_every_parameter_gradient_against_independent_scalar_loss():
    assert assurance.gradient_audit()['parameter_coverage']==1

def test_predeclared_executable_semantic_mutations_are_detected():
    report=assurance.mutation_controls()
    assert report['killed']==len(assurance.MUTANTS) and report['survived']==0

@pytest.mark.parametrize('kind',['duplicate_node','dangling_edge','node_limit','edge_limit'])
def test_graph_adversarial_topology_and_bounds(kind):
    graph=assurance.graph(17)
    if kind=='duplicate_node':graph['nodes'].append(graph['nodes'][0].copy())
    elif kind=='dangling_edge':graph['edges'][0]['to']='missing'
    elif kind=='node_limit':graph['nodes']=[{'id':str(i),'kind':'role'}for i in range(1201)]
    else:graph['edges']=graph['edges']*20001
    with pytest.raises(ValueError):nn.tensors(graph)

@pytest.mark.parametrize('kind',['prediction_after_outcome','decision_before_prediction','invalid_stage','invalid_version','missing_provenance','nan_probability','duplicate_record'])
def test_adversarial_forecast_provenance_and_temporal_leakage(kind):
    from tests.test_prospective_methods import forecast_row
    row=forecast_row();records=[row]
    if kind=='prediction_after_outcome':row['created_at']='2030-01-01T00:00:00Z'
    elif kind=='decision_before_prediction':row['candidate_decided_at']='2020-01-01T00:00:00Z'
    elif kind=='invalid_stage':row['stage']='hire'
    elif kind=='invalid_version':row['model_version']='unknown'
    elif kind=='missing_provenance':row.pop('synthetic')
    elif kind=='nan_probability':row['prediction']['candidate_acceptance']['mean']=float('nan')
    else:records.append(row.copy())
    with pytest.raises(ValueError):assurance.pv.forecast_report({'records':records})
