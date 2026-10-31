"""After-close check that private evidence was uploaded during this session."""
import json,os,urllib.request
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from scripts.reconcile_paper_account import PaperReader
from analytics.private_evidence import REPOSITORY

def main():
    now=datetime.now(timezone.utc); day=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    calendar=PaperReader().get('/v2/calendar',{'start':day,'end':day})
    if not calendar:
        print('Non-trading day'); return
    token=os.getenv('GIT_TOKEN')
    if not token: raise RuntimeError('Evidence monitoring token missing')
    headers={'Authorization':'Bearer '+token,'User-Agent':'evidence-monitor'}
    req=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+'/commits?path=bundles&per_page=1',headers=headers)
    with urllib.request.urlopen(req,timeout=30) as response: commits=json.load(response)
    opening=datetime.fromisoformat(day+'T'+calendar[0]['open']).replace(tzinfo=ZoneInfo('America/New_York'))
    latest=datetime.fromisoformat(commits[0]['commit']['committer']['date'].replace('Z','+00:00')) if commits else None
    if latest is None or latest<opening: raise RuntimeError('No current-session private evidence upload')
    print('Current-session upload observed; this does not establish complete coverage')

if __name__=='__main__': main()
