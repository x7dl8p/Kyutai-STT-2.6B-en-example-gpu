import glob, os, json, shutil, time
import torch
from safetensors import safe_open
from safetensors.torch import save_file

base=r"C:\Users\Ali\.cache\huggingface\hub\models--Qwen--Qwen3-TTS-12Hz-1.7B-CustomVoice\snapshots"
snap=glob.glob(base+r"\*")[0]
out=r"C:\Users\ali\models\Qwen3-TTS-1.7B-CustomVoice-sharded"
os.makedirs(out, exist_ok=True)

# copy every non-safetensors file (config, tokenizer, spk/rvq assets, ...)
for name in os.listdir(snap):
    src=os.path.realpath(os.path.join(snap,name))
    if name.endswith(".safetensors") or os.path.isdir(src): continue
    shutil.copyfile(src, os.path.join(out,name))
    print("copied", name)

src=os.path.realpath(glob.glob(snap+r"\*.safetensors")[0])
SHARD=350*1024*1024
shards=[]; cur={}; cur_sz=0

def flush():
    global cur, cur_sz
    if not cur: return
    shards.append(cur); cur={}; cur_sz=0

t=time.time()
with safe_open(src, framework="pt", device="cpu") as f:
    meta=f.metadata() or {}
    for k in f.keys():
        v=f.get_tensor(k).clone().contiguous()
        nb=v.numel()*v.element_size()
        if cur_sz+nb > SHARD: flush()
        cur[k]=v; cur_sz+=nb
    flush()

total=sum(sum(t_.numel()*t_.element_size() for t_ in s.values()) for s in shards)
n=len(shards); index={"metadata":{"total_size":total},"weight_map":{}}
for i,s in enumerate(shards,1):
    fn=f"model-{i:05d}-of-{n:05d}.safetensors"
    save_file(s, os.path.join(out,fn), metadata={"format":"pt"})
    for k in s: index["weight_map"][k]=fn
    print(f"wrote {fn}  {sum(x.numel()*x.element_size() for x in s.values())/1e6:.0f} MB", flush=True)
    s.clear()
json.dump(index, open(os.path.join(out,"model.safetensors.index.json"),"w"), indent=2)
print(f"DONE {n} shards, {total/1e9:.2f} GB, {time.time()-t:.0f}s -> {out}")
