"""
LIN System v0.4 — ABQ Stress Simulation v3
Option C-revised:
  - FREEZE 期間 beta_Q gate 由 T_global 控制（Option C）
  - FREEZE 期間 dissipation 用 B_crit 替代 B_frozen
    dQ/dt_FREEZE = -delta_Q * Q * A_frozen * B_crit
  語義：Q 消散由治理閾值錨定，不被已受損的 B 拖累
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.integrate import solve_ivp

A_crit=0.6; B_crit=0.5
alpha_A=0.2; alpha_B=0.6
gamma_A=0.03; gamma_B=0.05
beta_Q=10.0; delta_Q=0.35

eta_Lambda=0.3; eta_PIM=0.2; eta_DDR=0.5; eta_R=0.4
theta_PIM=1.0; tau_sys=0.75; T_freeze=0.0

STABLE=0; FREEZE=1; DECOMPRESS=2; CONFIRM=3

def drift_score(t):
    if t <= 8.0: return t/8.0
    return max(0.0, 1.0-(t-8.0)/6.0)

def T_global(t):
    if t <= 8.0: return t/8.0
    return max(0.0, 1.0-(t-8.0)/6.0)

def lambda_ab(t): return 1.0 if t>=5.0 else 0.0
def PIM_norm(t):  return min(1.0, t/15.0)
def R_phase(t):   return max(0.1, 1.0-0.8*min(1.0, t/10.0))

def get_fdcs(Q, confirm_active):
    if Q >= 0.35:              return FREEZE
    if 0.001 < Q <= 0.15:
        if confirm_active:     return CONFIRM
        return DECOMPRESS
    return STABLE

def abq_ode(t, y, confirm_time):
    A, B, Q, cflag = y
    A=np.clip(A,0,1); B=np.clip(B,0,1)
    Q=np.clip(Q,0,1); cflag=np.clip(cflag,0,1)

    confirm_active = (cflag > 0.5)
    fdcs = get_fdcs(Q, confirm_active)

    Tg=T_global(t); ds=drift_score(t)
    lam=lambda_ab(t); pim=PIM_norm(t); R=R_phase(t)

    alpha_A_eff = alpha_A*(1+eta_Lambda*lam)*(1+eta_PIM*pim/theta_PIM)
    alpha_B_eff = alpha_B*(1+eta_DDR*ds/0.40)
    beta_Q_eff  = beta_Q *(1+eta_R*max(0, tau_sys-R))

    gate_A = max(0.0, A_crit-A)
    gate_B = max(0.0, B_crit-B)
    pressure_on = (Tg > T_freeze)

    if fdcs == FREEZE:
        dA = 0.0
        dB = 0.0
        # C-revised: dissipation anchored to B_crit, not B_frozen
        if pressure_on:
            dQ = beta_Q_eff*gate_A*gate_B - delta_Q*Q*A*B_crit
        else:
            dQ = -delta_Q*Q*A*B_crit
    else:
        dA = -alpha_A_eff*(Tg-T_freeze)*A + gamma_A*(1-Q)*(1-A)
        dB = -alpha_B_eff*ds*B            + gamma_B*(1-Q)*(1-B)
        if pressure_on:
            dQ = beta_Q_eff*gate_A*gate_B - delta_Q*Q*A*B
        else:
            dQ = -delta_Q*Q*A*B
        if fdcs in (DECOMPRESS, CONFIRM) and confirm_time and t>=confirm_time:
            dA += 0.15*(1-A)

    dcflag = 1.0 if (confirm_time and t>=confirm_time and cflag<0.5) else 0.0
    return [dA, dB, dQ, dcflag]

def simulate(confirm_time=None, t_end=80.0, dt=0.02):
    y0=[1.0,1.0,0.0,0.0]
    sol=solve_ivp(abq_ode,[0,t_end],y0,args=(confirm_time,),
                  method='RK45',max_step=dt,dense_output=True)
    t=sol.t; A,B,Q,cf=sol.y
    fdcs=np.array([get_fdcs(Q[i],cf[i]>0.5) for i in range(len(t))])
    return t,A,B,Q,fdcs

t1,A1,B1,Q1,f1 = simulate(confirm_time=None)
t2,A2,B2,Q2,f2 = simulate(confirm_time=32.0)

def first_cross(t,x,thr,d):
    for i in range(1,len(t)):
        if d=='above' and x[i-1]<=thr<x[i]: return t[i]
        if d=='below' and x[i-1]>=thr>x[i]: return t[i]
    return None

print("=== C-revised dissipation results ===\n")
for label,t,A,B,Q,f,ct in [
    ("SP-2 no confirm",     t1,A1,B1,Q1,f1,None),
    ("Recovery confirm@32s",t2,A2,B2,Q2,f2,32.0)]:

    freeze_t = first_cross(t, Q, 0.35,'above')
    if freeze_t:
        t_after = t[t>freeze_t]; Q_after=Q[t>freeze_t]
        decomp_t = first_cross(t_after, Q_after, 0.15,'below')
    else:
        decomp_t = None
    stable_t = first_cross(t, A, A_crit,'above')

    print(f"=== {label} ===")
    print(f"  FREEZE entry:      t = {freeze_t:.2f}s" if freeze_t else "  FREEZE: not triggered")
    print(f"  DECOMPRESS entry:  t = {decomp_t:.2f}s" if decomp_t else "  DECOMPRESS: not reached")
    print(f"  A crosses A_crit:  t = {stable_t:.2f}s" if stable_t else "  A_crit recovery: not crossed")
    print(f"  Final  A={A[-1]:.3f}  B={B[-1]:.3f}  Q={Q[-1]:.4f}")

    if freeze_t:
        idx=np.argmin(np.abs(t-freeze_t))
        t_min = np.log(0.35/0.15)/(delta_Q*A[idx]*B_crit) if A[idx]>1e-6 else float('inf')
        print(f"  A,B at FREEZE: {A[idx]:.3f},{B[idx]:.3f}  →  t_min_FREEZE(C-rev) = {t_min:.1f}s")
    print()

# ── Figure ────────────────────────────────────────────────────────────────────
fig=plt.figure(figsize=(15,11))
fig.patch.set_facecolor('#0d1117')
gs=gridspec.GridSpec(3,2,hspace=0.46,wspace=0.30,
                     left=0.07,right=0.97,top=0.93,bottom=0.07)

cA='#4fc3f7'; cB='#81c784'; cQ='#ffb74d'
cAc='#ef5350'; cBc='#ab47bc'; cCF='#66bb6a'
fdcs_bg={FREEZE:'#3a1500',DECOMPRESS:'#001a2a',CONFIRM:'#001a10'}

def shade(ax,t,f):
    i=0
    while i<len(f):
        s=f[i]; j=i
        while j<len(f) and f[j]==s: j+=1
        if s in fdcs_bg:
            ax.axvspan(t[i],t[min(j,len(t)-1)],alpha=0.4,color=fdcs_bg[s],zorder=0)
        i=j

titles=['Path SP-2  (no confirm — sustained protection)',
        'Path Recovery  (confirm() at t = 32s)']

for col,(t,A,B,Q,f,ct) in enumerate([
        (t1,A1,B1,Q1,f1,None),(t2,A2,B2,Q2,f2,32.0)]):

    # ── A, B ──
    ax=fig.add_subplot(gs[0,col])
    ax.set_facecolor('#0d1117'); shade(ax,t,f)
    ax.plot(t,A,color=cA,lw=2,label='A  Authority')
    ax.plot(t,B,color=cB,lw=2,label='B  Boundary')
    ax.axhline(A_crit,color=cAc,lw=1,ls='--',alpha=0.85,label=f'A_crit {A_crit}')
    ax.axhline(B_crit,color=cBc,lw=1,ls='--',alpha=0.85,label=f'B_crit {B_crit}')
    if ct: ax.axvline(ct,color=cCF,lw=1.5,ls=':',label='confirm()')
    ax.set_xlim(0,80); ax.set_ylim(-0.05,1.12)
    ax.set_title(titles[col],color='white',fontsize=9.5,pad=6)
    ax.set_ylabel('A, B',color='#aaa',fontsize=9)
    ax.tick_params(colors='#888',labelsize=8)
    [sp.set_color('#333') for sp in ax.spines.values()]
    ax.legend(fontsize=7.5,loc='center right',
              facecolor='#1a1a2e',edgecolor='#444',labelcolor='white',ncol=2)
    ax.grid(axis='y',color='#1e1e1e',lw=0.6)

    # ── Q ──
    ax=fig.add_subplot(gs[1,col])
    ax.set_facecolor('#0d1117'); shade(ax,t,f)
    ax.plot(t,Q,color=cQ,lw=2.5,label='Q  Quiescence')
    ax.axhline(0.35,color='#ff6b35',lw=1.2,ls='--',alpha=0.9,label='FREEZE  0.35')
    ax.axhline(0.15,color='#26c6da',lw=1.2,ls='--',alpha=0.9,label='DECOMPRESS  0.15')
    if ct: ax.axvline(ct,color=cCF,lw=1.5,ls=':')
    ax.set_xlim(0,80); ax.set_ylim(-0.02,0.65)
    ax.set_ylabel('Q',color='#aaa',fontsize=9)
    ax.tick_params(colors='#888',labelsize=8)
    [sp.set_color('#333') for sp in ax.spines.values()]
    ax.legend(fontsize=7.5,loc='upper right',
              facecolor='#1a1a2e',edgecolor='#444',labelcolor='white')
    ax.grid(axis='y',color='#1e1e1e',lw=0.6)

    # ── Row 2 ──
    ax=fig.add_subplot(gs[2,col])
    ax.set_facecolor('#0d1117')
    if col==0:
        tpl=np.linspace(0,80,600)
        ax.plot(tpl,[T_global(s) for s in tpl],color='#ef9a9a',lw=1.8,label='T_global')
        ax.plot(tpl,[drift_score(s) for s in tpl],color='#ffe082',lw=1.8,ls='--',label='drift_score')
        ax.axvline(14,color='#888',lw=0.8,ls=':',alpha=0.6)
        ax.text(14.3,0.85,'pressure off',color='#888',fontsize=7.5)
        ax.set_ylabel('pressure signals',color='#aaa',fontsize=9)
        ax.set_title('External pressure (Option C gate)',color='white',fontsize=9,pad=4)
        ax.legend(fontsize=7.5,facecolor='#1a1a2e',edgecolor='#444',labelcolor='white')
        ax.set_xlim(0,80); ax.set_ylim(-0.05,1.15)
    else:
        sc=ax.scatter(A,B,c=Q,cmap='plasma',s=5,vmin=0,vmax=0.5,zorder=3)
        ax.axvline(A_crit,color=cAc,lw=1,ls='--',alpha=0.7)
        ax.axhline(B_crit,color=cBc,lw=1,ls='--',alpha=0.7)
        # annotate quadrants
        ax.text(0.62,0.55,'STABLE',color='#4fc3f7',fontsize=7.5,alpha=0.7)
        ax.text(0.05,0.55,'A-SPI',color='#ef5350',fontsize=7.5,alpha=0.7)
        ax.text(0.62,0.05,'B-SPI',color='#ab47bc',fontsize=7.5,alpha=0.7)
        ax.text(0.05,0.05,'FULL SPI',color='#ff6b35',fontsize=7.5,alpha=0.7)
        ax.set_xlabel('A  Authority',color='#aaa',fontsize=9)
        ax.set_ylabel('B  Boundary',color='#aaa',fontsize=9)
        ax.set_title('A–B phase portrait  (colour = Q)',color='white',fontsize=9,pad=4)
        cb=fig.colorbar(sc,ax=ax,pad=0.02)
        cb.ax.tick_params(colors='#888',labelsize=7)
        cb.set_label('Q',color='#aaa',fontsize=8)
        ax.plot(A[0],B[0],'o',color='#66bb6a',ms=7,zorder=5,label='start')
        ax.plot(A[-1],B[-1],'s',color='#ef5350',ms=7,zorder=5,label='end')
        ax.legend(fontsize=7.5,facecolor='#1a1a2e',edgecolor='#444',labelcolor='white')

    ax.set_xlabel('time (s)',color='#aaa',fontsize=9)
    ax.tick_params(colors='#888',labelsize=8)
    [sp.set_color('#333') for sp in ax.spines.values()]
    ax.grid(color='#1e1e1e',lw=0.6)

from matplotlib.patches import Patch
fig.legend(handles=[
    Patch(facecolor='#3a1500',alpha=0.7,label='FREEZE'),
    Patch(facecolor='#001a2a',alpha=0.7,label='DECOMPRESS'),
    Patch(facecolor='#001a10',alpha=0.7,label='CONFIRM'),
],loc='lower center',ncol=3,
   facecolor='#0d1117',edgecolor='#444',labelcolor='white',
   fontsize=9,bbox_to_anchor=(0.5,0.002))

fig.suptitle(
    'LIN System v0.4 — ABQ Stress Simulation v3  |  '
    'Option C-revised: Governance-Anchored Dissipation  |  dQ_FREEZE = −δQ·Q·A·B_crit',
    color='white',fontsize=10.5,y=0.977)

plt.savefig('/mnt/user-data/outputs/abq_stress_simulation_v3.png',
            dpi=150,bbox_inches='tight',facecolor='#0d1117')
print("Figure saved.")

# ── Extended 120s final figure ────────────────────────────────────────────────
from scipy.integrate import solve_ivp as _solve

def simulate_120(confirm_time=None):
    sol=_solve(abq_ode,[0,120],[1.0,1.0,0.0,0.0],args=(confirm_time,),
               method='RK45',max_step=0.05)
    t=sol.t; A,B,Q,cf=sol.y
    fdcs=np.array([get_fdcs(Q[i],cf[i]>0.5) for i in range(len(t))])
    return t,A,B,Q,fdcs

t1,A1,B1,Q1,f1 = simulate_120(None)
t2,A2,B2,Q2,f2 = simulate_120(32.0)

fig2=plt.figure(figsize=(15,10))
fig2.patch.set_facecolor('#0d1117')
gs2=gridspec.GridSpec(2,2,hspace=0.42,wspace=0.28,
                      left=0.07,right=0.97,top=0.93,bottom=0.08)

STABLE2=0
fdcs_bg2={1:'#3a1500',2:'#001a2a',3:'#001a10'}

def shade2(ax,t,f):
    i=0
    while i<len(f):
        s=f[i]; j=i
        while j<len(f) and f[j]==s: j+=1
        if s in fdcs_bg2:
            ax.axvspan(t[i],t[min(j,len(t)-1)],alpha=0.4,color=fdcs_bg2[s],zorder=0)
        i=j

for col,(t,A,B,Q,f,ct,title) in enumerate([
    (t1,A1,B1,Q1,f1,None,'Path SP-2  ·  no confirm  →  autonomous recovery'),
    (t2,A2,B2,Q2,f2,32.0,'Path Recovery  ·  confirm() at t = 32s  →  A fully restored'),
]):
    # A, B
    ax=fig2.add_subplot(gs2[0,col])
    ax.set_facecolor('#0d1117'); shade2(ax,t,f)
    ax.plot(t,A,color='#4fc3f7',lw=2,  label='A  Authority')
    ax.plot(t,B,color='#81c784',lw=2,  label='B  Boundary')
    ax.axhline(0.6,color='#ef5350',lw=1,ls='--',alpha=0.8,label='A_crit 0.6')
    ax.axhline(0.5,color='#ab47bc',lw=1,ls='--',alpha=0.8,label='B_crit 0.5')
    if ct: ax.axvline(ct,color='#66bb6a',lw=1.5,ls=':',label='confirm()')
    # annotate key events
    for tmark,label_str,ypos in [(7.3,'FREEZE',0.08),(84.3,'DECOMP',0.08)]:
        ax.axvline(tmark,color='#888',lw=0.7,ls=':',alpha=0.5)
        ax.text(tmark+0.5,ypos,label_str,color='#aaa',fontsize=7)
    ax.set_xlim(0,120); ax.set_ylim(-0.05,1.12)
    ax.set_title(title,color='white',fontsize=9,pad=5)
    ax.set_ylabel('A, B',color='#aaa',fontsize=9)
    ax.set_xlabel('time (s)',color='#aaa',fontsize=9)
    ax.tick_params(colors='#888',labelsize=8)
    [sp.set_color('#333') for sp in ax.spines.values()]
    ax.legend(fontsize=7.5,loc='center right',
              facecolor='#1a1a2e',edgecolor='#444',labelcolor='white',ncol=2)
    ax.grid(axis='y',color='#1e1e1e',lw=0.6)

    # Q
    ax=fig2.add_subplot(gs2[1,col])
    ax.set_facecolor('#0d1117'); shade2(ax,t,f)
    ax.plot(t,np.clip(Q,0,5),color='#ffb74d',lw=2.5,label='Q  Quiescence')
    ax.axhline(0.35,color='#ff6b35',lw=1.2,ls='--',alpha=0.9,label='FREEZE  0.35')
    ax.axhline(0.15,color='#26c6da',lw=1.2,ls='--',alpha=0.9,label='DECOMPRESS  0.15')
    if ct: ax.axvline(ct,color='#66bb6a',lw=1.5,ls=':')
    # annotate FREEZE duration
    ax.annotate('',xy=(84,0.38),xytext=(7.3,0.38),
                arrowprops=dict(arrowstyle='<->',color='#ff6b35',lw=1.2))
    ax.text(40,0.41,'FREEZE duration ≈ 77s',color='#ff6b35',fontsize=7.5,ha='center')
    ax.set_xlim(0,120); ax.set_ylim(-0.05,5.2)
    ax.set_ylabel('Q',color='#aaa',fontsize=9)
    ax.set_xlabel('time (s)',color='#aaa',fontsize=9)
    ax.tick_params(colors='#888',labelsize=8)
    [sp.set_color('#333') for sp in ax.spines.values()]
    ax.legend(fontsize=7.5,loc='upper right',
              facecolor='#1a1a2e',edgecolor='#444',labelcolor='white')
    ax.grid(axis='y',color='#1e1e1e',lw=0.6)

from matplotlib.patches import Patch
fig2.legend(handles=[
    Patch(facecolor='#3a1500',alpha=0.7,label='FREEZE  (dA=dB=0, dQ=−δQ·Q·A·B_crit)'),
    Patch(facecolor='#001a2a',alpha=0.7,label='DECOMPRESS  (Q∈(0.15,0.35))'),
    Patch(facecolor='#001a10',alpha=0.7,label='CONFIRM  (human confirm active)'),
],loc='lower center',ncol=3,
   facecolor='#0d1117',edgecolor='#444',labelcolor='white',
   fontsize=8.5,bbox_to_anchor=(0.5,0.002))

fig2.suptitle(
    'LIN System v0.4 — ABQ Step 2 Final Verification  |  '
    'C-revised: FREEZE dissipation anchored to B_crit\n'
    'FREEZE entry t=7.3s  ·  DECOMPRESS t=84.3s  ·  Full recovery by t≈120s',
    color='white',fontsize=10,y=0.978)

plt.savefig('/mnt/user-data/outputs/abq_stress_final.png',
            dpi=150,bbox_inches='tight',facecolor='#0d1117')
print("Final figure saved.")
