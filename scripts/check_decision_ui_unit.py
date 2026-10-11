"""Record actual Node checks and affected Python suite results."""
import json,re,subprocess,time,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'validation/reports/current'

def main():
    command=[str(ROOT/'.tools/node-v24.21.0-win-x64/node.exe'),'--test','--test-reporter=tap','tests/decision-ui.mjs']
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    passed=re.search(r'^# pass (\d+)$',result.stdout,re.M);failed=re.search(r'^# fail (\d+)$',result.stdout,re.M)
    assert result.returncode==0 and passed and failed and int(failed[1])==0,result.stdout+result.stderr
    suites=[]
    for filename in ('decision-ui-cpu.xml','graph-explanation.xml'):
        xml=ET.parse(OUT/filename).getroot();suite=xml.find('testsuite')if xml.tag=='testsuites'else xml
        assert int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
        suites.append({'file':filename,'tests':int(suite.attrib['tests']),'failures':0,'errors':0})
    report={'passed':True,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'node_passed':int(passed[1]),'node_failed':0,'python_suites':suites,'llm_calls':0,'scope':'affected numerical methods + full requirement/inventory projection + scoped navigation and exact artifact edges; existing tests not summed twice'}
    (OUT/'decision-ui-unit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (OUT/'decision-ui-node.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':main()
