"""Check destination privacy and write permission without logging credentials."""
import json
import os
import urllib.request

if __name__=='__main__':
    token=os.getenv('GIT_TOKEN','').strip()
    if not token: raise SystemExit('GIT_TOKEN missing; private evidence unavailable')
    request=urllib.request.Request('https://api.github.com/repos/Shashwat-911/Autonomous-Stock-Trading-Evidence',
        headers={'Authorization':'Bearer '+token,'User-Agent':'evidence-preflight','Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request,timeout=30) as response: repository=json.load(response)
    except Exception as exc:
        raise SystemExit('Private evidence preflight failed: '+type(exc).__name__) from None
    if repository.get('private') is not True or not repository.get('permissions',{}).get('push'):
        raise SystemExit('Evidence destination must be private and writable')
    print('Private evidence repository verified; write permission available')
