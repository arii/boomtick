import os
def emit_summary(title:str,status:str,data:dict,elapsed_seconds:float|None=None):
    lines=[f"## {title}",f"**Status:** {'✅' if status=='success' else '❌'} {status.upper()}"]
    if elapsed_seconds is not None: lines.append(f"**Duration:** {elapsed_seconds:.1f}s")
    for k,v in data.items(): lines.append(f"**{k}:** {v}")
    out='\n'.join(lines)+'\n\n'
    path=os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path,'a') as f: f.write(out)
    else:
        print(out,end='')
