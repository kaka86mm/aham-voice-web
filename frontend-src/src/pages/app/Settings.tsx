import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchSettings, patchSettings } from "@/api/endpoints";
import { readApiError } from "@/api/client";
import { PageHead } from "@/components/PageHead";
import { Button } from "@/components/Button";
import { Status } from "@/components/Status";
import { Diag } from "@/components/Diag";
import { Icon } from "@/components/Icon";

export function Settings() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });

  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // Seed the editable base/model from the server once loaded. The key itself is
  // never returned by the backend, so its field always starts blank.
  useEffect(() => {
    if (settings.data) {
      setApiBase(settings.data.deepseek_api_base);
      setModel(settings.data.deepseek_model);
    }
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () =>
      patchSettings({
        ...(apiKey.trim() ? { deepseek_api_key: apiKey.trim() } : {}),
        deepseek_api_base: apiBase.trim(),
        deepseek_model: model.trim(),
      }),
    onSuccess: () => {
      setApiKey("");
      setInfo("已保存。会议纪要、对话情绪语义分析、改纪要将使用该配置。");
      setError(null);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => {
      setError(readApiError(err));
      setInfo(null);
    },
  });

  const clearKey = useMutation({
    mutationFn: () => patchSettings({ deepseek_api_key: "" }),
    onSuccess: () => {
      setApiKey("");
      setInfo("已清除 API Key。纪要相关功能将不可用，转写与声学情绪不受影响。");
      setError(null);
      qc.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (err) => setError(readApiError(err)),
  });

  const configured = settings.data?.deepseek_configured ?? false;

  return (
    <div className="page-body">
      <PageHead
        title="设置"
        subtitle="本地单机运行。转写与声学情绪完全离线；会议纪要与情绪语义分析需要配置云端大模型（DeepSeek）API Key。"
      />

      {error && <Diag code="SET_E">{error}</Diag>}
      {info && <Diag code="SET_OK" tone="info">{info}</Diag>}

      <section
        style={{
          maxWidth: 640,
          border: "1px solid var(--border-default)",
          borderRadius: "var(--radius-md)",
          background: "var(--bg-surface)",
          padding: "var(--space-5)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-4)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <h3 style={{ margin: 0, fontSize: "var(--text-base)", fontWeight: "var(--weight-semibold)" }}>
            DeepSeek 大模型
          </h3>
          <Status tone={configured ? "moss" : "amber"}>
            {configured ? "已配置" : "未配置"}
          </Status>
        </div>

        <p className="meta" style={{ margin: 0, fontSize: "var(--text-xs)", color: "var(--fg-subtle)" }}>
          API Key 只保存在本机（应用数据目录的 config.json），不会上传，也不会在此页回显。
          前往 platform.deepseek.com 获取自己的 API Key。
        </p>

        <label style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <span className="meta" style={{ fontSize: "var(--text-xs)" }}>API Key</span>
          <input
            className="field"
            type="password"
            placeholder={configured ? "已配置（留空则保持不变）" : "sk-..."}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            autoComplete="off"
          />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <span className="meta" style={{ fontSize: "var(--text-xs)" }}>API Base（一般无需修改）</span>
          <input
            className="field"
            type="text"
            placeholder="https://api.deepseek.com"
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
          />
        </label>

        <label style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          <span className="meta" style={{ fontSize: "var(--text-xs)" }}>模型</span>
          <input
            className="field"
            type="text"
            placeholder="deepseek-v4-pro"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        </label>

        <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
          <Button
            variant="primary"
            size="sm"
            loading={save.isPending}
            onClick={() => { setError(null); setInfo(null); save.mutate(); }}
          >
            <Icon name="save" size={14} /> 保存
          </Button>
          {configured && (
            <Button
              variant="ghost"
              size="sm"
              loading={clearKey.isPending}
              onClick={() => { setError(null); setInfo(null); clearKey.mutate(); }}
            >
              清除 Key
            </Button>
          )}
        </div>
      </section>
    </div>
  );
}
