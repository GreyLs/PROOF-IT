import httpx,time,json
t=time.perf_counter()
r=httpx.post('http://127.0.0.1:11434/api/chat',json={'model':'qwen3:8b','stream':False,'think':False,'messages':[{'role':'user','content':'Return JSON only: {"ready":true} /no_think'}],'format':'json','options':{'num_ctx':4096,'num_predict':40,'num_gpu':999}},timeout=180)
print(r.status_code,r.text[:700],round(time.perf_counter()-t,2))
