"use client";

import { useActionState } from "react";

import { loginAction } from "@/app/actions/auth";
import Button from "@/components/ui/button";
import { TextField } from "@/components/ui/field";

const initialState = { error: "" };

export default function LoginForm() {
  const [state, formAction, pending] = useActionState(loginAction, initialState);

  return (
    <main className="grid min-h-screen place-items-center bg-[#06100c] p-5">
      <section className="w-full max-w-md overflow-hidden rounded-[28px] border border-white/10 bg-white/[0.07] shadow-[0_24px_80px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.08)] backdrop-blur-2xl" aria-labelledby="login-title">
        <div className="flex min-h-14 items-center gap-3 border-b border-white/10 bg-white/[0.04] px-5">
          <span className="size-2 rounded-full bg-emerald-300" aria-hidden="true" />
          <span className="text-xs font-black tracking-[0.16em] text-white/60">本機安全入口</span>
        </div>
        <div className="grid gap-4 p-5">
          <p className="m-0 text-xs font-black tracking-[0.16em] text-white/55">PHYTO-AUTOSCOPY / CHLOROCULUS</p>
          <h1 id="login-title" className="m-0 text-2xl font-black text-white">控制台登入</h1>
          <p className="m-0 leading-7 text-white/65">請輸入本機操作密碼。硬體控制請求只會由受驗證的 Next.js 服務轉送。</p>
          <form action={formAction} className="grid gap-3">
            <TextField id="operator-password" label="操作密碼" name="password" type="password" autoComplete="current-password" required />
            {state?.error ? <p className="m-0 border-l-2 border-rose-400 pl-3 text-sm text-rose-300" role="alert">{state.error}</p> : null}
            <Button variant="primary" type="submit" disabled={pending}>
              {pending ? "驗證中…" : "進入控制台"}
            </Button>
          </form>
        </div>
      </section>
    </main>
  );
}
