import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/Button";
import { Field, FormRow } from "@/components/Field";
import { Diag } from "@/components/Diag";
import { api, readApiError } from "@/api/client";

// 单密码登录页。后端 AHAMVOICE_ACCESS_PASSWORD 非空时启用密码门，
// 登录成功 set cookie（httpOnly），后续请求带 cookie 放行。
// 密码门未启用时这个页面不会被触发（401 拦截才跳这里）。
export function Login() {
  const nav = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!password) return;
    setError(null);
    setLoading(true);
    try {
      await api.post("/auth/login", { password });
      nav("/");
    } catch (err) {
      setError(readApiError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="auth-card" onSubmit={submit}>
      <h1 className="auth-card__title">访问密码</h1>
      <p className="auth-card__hint">本服务需要密码访问。请输入访问密码。</p>
      {error && <Diag code="AUTH_E_LOGIN">{error}</Diag>}
      <FormRow label="访问密码">
        <Field
          type="password"
          value={password}
          autoComplete="current-password"
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
      </FormRow>
      <Button type="submit" variant="primary" loading={loading} disabled={!password}>
        进入
      </Button>
    </form>
  );
}
