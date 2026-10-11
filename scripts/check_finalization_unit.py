"""Persist actual Node locale-integrity checks, without counting reruns twice."""
import json,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'
def main():
 command=[str(ROOT/'.tools/node-v24.21.0-win-x64/node.exe'),'--test','--test-reporter=junit','tests/locale-quality.mjs']
 result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=30)
 assert result.returncode==0,result.stderr+result.stdout
 tree=ET.fromstring(result.stdout)
 cases=list(tree.iter('testcase'));tests=len(cases)
 failures=sum(case.find('failure')is not None for case in cases);errors=sum(case.find('error')is not None for case in cases)
 # Node's root-level testcase JUnit is normalized for suite-based consumers.
 suite=ET.Element('testsuite',{'name':'node locale-quality','tests':str(tests),'failures':str(failures),'errors':str(errors),'skipped':'0'})
 suite.extend(cases);normalized=ET.Element('testsuites');normalized.append(suite)
 (OUT/'finalization-node.xml').write_bytes(ET.tostring(normalized,encoding='utf-8',xml_declaration=True))
 assert tests==5 and failures==errors==0
 report={'passed':True,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'tests':tests,'failures':failures,
  'scope':'build-time source/catalog SHA binding and fail-closed locale readiness','llm_calls':0}
 (OUT/'finalization-node.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
