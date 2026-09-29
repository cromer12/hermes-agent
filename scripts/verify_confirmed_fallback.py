#!/usr/bin/env python3
"""End-to-end verifier for consent-gated automatic fallback."""
from __future__ import annotations
import json,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from openai import OpenAI
from run_agent import AIAgent

class Counter:
    def __init__(self): self.bodies=[]
class Handler(BaseHTTPRequestHandler):
    counter=None
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0')); body=self.rfile.read(n); self.counter.bodies.append(body)
        request=json.loads(body)
        if request.get('stream'):
            events=[
                {"id":"chatcmpl-fallback","object":"chat.completion.chunk","created":int(time.time()),"model":"fallback-model","choices":[{"index":0,"delta":{"role":"assistant","content":"FALLBACK_SENTINEL"},"finish_reason":None}]},
                {"id":"chatcmpl-fallback","object":"chat.completion.chunk","created":int(time.time()),"model":"fallback-model","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]},
            ]
            raw=("".join("data: "+json.dumps(event)+"\n\n" for event in events)+"data: [DONE]\n\n").encode()
            content_type='text/event-stream'
        else:
            payload={"id":"chatcmpl-fallback","object":"chat.completion","created":int(time.time()),"model":"fallback-model","choices":[{"index":0,"message":{"role":"assistant","content":"FALLBACK_SENTINEL"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}
            raw=json.dumps(payload).encode(); content_type='application/json'
        self.send_response(200); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*args): return

def make_agent():
    agent=AIAgent(base_url='http://127.0.0.1:9/v1',api_key='dead',provider='openai',api_mode='chat_completions',model='dead-primary',max_iterations=4,quiet_mode=True,skip_context_files=True,skip_memory=True,fallback_model=[{"provider":"openai","model":"fallback-model","require_confirmation":True}])
    agent._api_max_retries=1; agent._persist_session=lambda *a,**k:None; agent._save_trajectory=lambda *a,**k:None
    return agent

def main():
    counter=Counter(); Handler.counter=counter; server=ThreadingHTTPServer(('127.0.0.1',0),Handler); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    fallback_client=OpenAI(api_key='fallback',base_url=f'http://127.0.0.1:{server.server_port}/v1',timeout=5,max_retries=0)
    failures=[]
    try:
        with patch('run_agent.get_tool_definitions',return_value=[]),patch('run_agent.check_toolset_requirements',return_value={}):
            def arm(agent):
                def activate(*_args,**_kwargs):
                    agent.client=fallback_client; agent.base_url=str(fallback_client.base_url); agent.api_key='fallback'; agent.model='fallback-model'; agent.provider='openai'; agent.api_mode='chat_completions'; agent._client_kwargs={"api_key":"fallback","base_url":str(fallback_client.base_url)}; agent._transport_cache.clear(); agent._fallback_index=1; agent._fallback_activated=True; agent._fallback_confirmation_pending={"provider":"openai","model":"fallback-model"}; return True
                agent._try_activate_fallback=activate
                return agent
            consent_agent=arm(make_agent()); first=consent_agent.run_conversation('Return the fallback sentinel only if you receive this context.')
            pre_consent_count=len(counter.bodies)
            if pre_consent_count: failures.append('fallback_called_before_consent')
            if first.get('fallback_confirmation_required') is not True or 'continue on Tiiny' not in first.get('final_response',''): failures.append('pause_prompt_missing')
            second=consent_agent.run_conversation('continue on Tiiny',conversation_history=first.get('messages'))
            if second.get('final_response')!='FALLBACK_SENTINEL': failures.append('consent_did_not_resume')
            if len(counter.bodies)!=1: failures.append('consent_request_count_wrong')
            body=json.loads(counter.bodies[0]) if counter.bodies else {}
            message_contents=[str(message.get('content','')) for message in body.get('messages',[]) if isinstance(message,dict)]
            if not any('Return the fallback sentinel' in content for content in message_contents): failures.append('thread_context_missing_after_consent')

            before=len(counter.bodies); wait_agent=arm(make_agent()); wait_first=wait_agent.run_conversation('Do not send this to fallback before consent.')
            if len(counter.bodies)!=before or wait_first.get('fallback_confirmation_required') is not True: failures.append('wait_setup_leaked')
            waited=wait_agent.run_conversation('wait for cloud',conversation_history=wait_first.get('messages'))
            if len(counter.bodies)!=before: failures.append('wait_called_fallback')
            if waited.get('fallback_waiting_for_cloud') is not True: failures.append('wait_ack_missing')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
    result={"ok":not failures,"failures":failures,"requests_before_consent":pre_consent_count,"consent_requests":before-pre_consent_count,"wait_request_delta":len(counter.bodies)-before,"diagnostic":{"consent_final":second.get('final_response') if 'second' in locals() else None,"consent_completed":second.get('completed') if 'second' in locals() else None,"model":getattr(consent_agent,'model',None) if 'consent_agent' in locals() else None,"base_url":str(getattr(consent_agent,'base_url','')) if 'consent_agent' in locals() else None,"message_previews":[content[:160] for content in message_contents] if 'message_contents' in locals() else []}}
    print(json.dumps(result,sort_keys=True,separators=(',',':'))); return 0 if result['ok'] else 1
if __name__=='__main__': raise SystemExit(main())
