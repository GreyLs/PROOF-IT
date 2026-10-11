"""Operator-only prepared adapter; no request occurs without a rights manifest."""
import argparse
import asyncio
import json
from pathlib import Path
from intelligence import economic_sources

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--index',default='IMOEX',choices=sorted(economic_sources.INDEXES))
 parser.add_argument('--from',dest='start',required=True)
 parser.add_argument('--till',required=True)
 parser.add_argument('--output',type=Path,required=True)
 args=parser.parse_args()
 if args.output.exists():parser.error('Output must be a new file')
 result=asyncio.run(economic_sources.fetch({'index':args.index,'from':args.start,'till':args.till}))
 with args.output.open('x',encoding='utf-8')as file:
  json.dump(result,file,ensure_ascii=False,indent=2,allow_nan=False);file.write('\n')
 print(json.dumps({'status':result['status'],'ranking_effect':0,'forecast_effect':0}))
if __name__=='__main__':main()
