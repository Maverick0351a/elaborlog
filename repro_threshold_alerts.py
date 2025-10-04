import subprocess, sys, tempfile, time, os, json

def main():
    td = tempfile.TemporaryDirectory()
    log = os.path.join(td.name, 'a.log')
    with open(log,'w',encoding='utf-8') as f:
        f.write('ERROR something bad happened code=42 user=7\n')
    jsonl = os.path.join(td.name,'alerts.jsonl')
    proc = subprocess.Popen([
        sys.executable,'-m','elaborlog.cli','tail',log,'--threshold','0.0','--burn-in','0','--jsonl',jsonl
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(0.3)
        for i in range(8):
            with open(log,'a',encoding='utf-8') as f:
                f.write(f'ERROR something bad happened code={40+i} user={7+i}\n')
            time.sleep(0.05)
        deadline=time.time()+3
        while time.time()<deadline:
            if os.path.exists(jsonl) and os.path.getsize(jsonl)>0:
                break
            time.sleep(0.1)
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        if proc.poll() is None:
            proc.kill()
    print('jsonl exists', os.path.exists(jsonl), 'size', os.path.getsize(jsonl) if os.path.exists(jsonl) else -1)
    if os.path.exists(jsonl):
        content = open(jsonl,'r',encoding='utf-8').read().strip().splitlines()
        print('lines written:', len(content))
        for line in content[:3]:
            print('sample line:', line[:160])
    print('STDERR:')
    print(proc.stderr.read())

if __name__ == '__main__':
    main()
