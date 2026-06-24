import { type ReactNode, useEffect, useState } from "react";
import {
  api,
  type Deal,
  type GovernanceDecision,
  type GuardrailDecision,
  type GuardrailPolicy,
  type IntelligenceTool,
  type KnowledgeBase,
  type LeadScore,
  type LLMComplete,
  type RagHit,
  type VaultNote,
} from "../lib/api";
import { useAuth } from "../lib/auth";

type Tab = "llm" | "guardrails" | "rag" | "governance" | "scoring" | "vault";

const TABS: Array<[Tab, string]> = [
  ["llm", "LLM Bridge"],
  ["guardrails", "Guardrails"],
  ["rag", "RAG"],
  ["governance", "Governança"],
  ["scoring", "Lead score"],
  ["vault", "Vault"],
];

const pillFor = (value: string): string => {
  if (["approved", "allow", "ready", "quente"].includes(value)) return "green";
  if (["review", "handoff", "morno", "revise"].includes(value)) return "amber";
  if (["blocked", "block", "frio"].includes(value)) return "pink";
  return "cyan";
};

export default function Intelligence() {
  const { user } = useAuth();
  const agencyId = user!.agency_id;
  const [tab, setTab] = useState<Tab>("llm");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [tools, setTools] = useState<IntelligenceTool[]>([]);
  const [policies, setPolicies] = useState<GuardrailPolicy[]>([]);
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [notes, setNotes] = useState<VaultNote[]>([]);

  const [llmPrompt, setLlmPrompt] = useState("Resuma em uma frase o que o FGOS faz.");
  const [llmResult, setLlmResult] = useState<LLMComplete | null>(null);

  const [policyName, setPolicyName] = useState("Atendimento seguro");
  const [blocked, setBlocked] = useState("ignore previous instructions, system prompt, senha");
  const [guardUser, setGuardUser] = useState("Cliente pediu preço e quer falar hoje.");
  const [guardAnswer, setGuardAnswer] = useState("Claro, vou te explicar os planos sem expor dados sensíveis.");
  const [guardDecision, setGuardDecision] = useState<GuardrailDecision | null>(null);

  const [kbName, setKbName] = useState("Base comercial");
  const [kbDescription, setKbDescription] = useState("Produtos, FAQs e argumentos por agência.");
  const [kbId, setKbId] = useState("");
  const [docTitle, setDocTitle] = useState("FAQ inicial");
  const [docBody, setDocBody] = useState("O FGOS organiza CRM, atendimento, campanhas, social, BI e IA em uma plataforma modular.");
  const [ragQuestion, setRagQuestion] = useState("O que o FGOS organiza?");
  const [ragHits, setRagHits] = useState<RagHit[]>([]);
  const [ragAnswer, setRagAnswer] = useState<string | null>(null);

  const [govAction, setGovAction] = useState("Enviar follow-up automático para lead quente");
  const [govRegime, setGovRegime] = useState("semi");
  const [govImpact, setGovImpact] = useState("medium");
  const [govConfidence, setGovConfidence] = useState(0.78);
  const [govReversible, setGovReversible] = useState(true);
  const [govDecision, setGovDecision] = useState<GovernanceDecision | null>(null);

  const [scoreDealId, setScoreDealId] = useState("");
  const [scoreTitle, setScoreTitle] = useState("Lead quer automatizar atendimento este mês");
  const [scoreNotes, setScoreNotes] = useState("Sou o dono, tenho orçamento e preciso vender mais pelo WhatsApp.");
  const [scoreValue, setScoreValue] = useState(120000);
  const [score, setScore] = useState<LeadScore | null>(null);

  const [noteKind, setNoteKind] = useState("methodology");
  const [noteTitle, setNoteTitle] = useState("Como qualificar lead com IA");
  const [noteBody, setNoteBody] = useState("Passo: rodar BANT, aplicar governança e só então sugerir próxima ação.");
  const [noteTags, setNoteTags] = useState("ia,crm,bant");
  const [vaultQuery, setVaultQuery] = useState("qualificar lead");
  const [vaultHits, setVaultHits] = useState<RagHit[]>([]);

  async function reload() {
    const [toolResp, ps, ks, ds, ns] = await Promise.allSettled([
      api.intelligenceTools(),
      api.guardrailPolicies(),
      api.knowledgeBases(),
      api.deals(agencyId),
      api.vaultNotes(),
    ]);
    setTools(toolResp.status === "fulfilled" ? toolResp.value.tools : [
      { id: "llm_bridge", name: "LLM Bridge", status: "ready" },
      { id: "guardrails", name: "Guardrails", status: "offline", count: 0 },
      { id: "rag", name: "RAG por agência", status: "offline", count: 0 },
      { id: "governance", name: "Governança IA", status: "offline", count: 0 },
      { id: "lead_scoring", name: "BANT / Lead score", status: "offline", count: 0 },
      { id: "vault", name: "Vault operacional", status: "offline", count: 0 },
    ]);
    setPolicies(ps.status === "fulfilled" ? ps.value : []);
    setBases(ks.status === "fulfilled" ? ks.value : []);
    setDeals(ds.status === "fulfilled" ? ds.value : []);
    setNotes(ns.status === "fulfilled" ? ns.value : []);
    if ([toolResp, ps, ks, ds, ns].some((item) => item.status === "rejected")) {
      setNotice("Algumas leituras dependem do Postgres/migration 016; a aba LLM continua disponível.");
    }
    const loadedBases = ks.status === "fulfilled" ? ks.value : [];
    const loadedDeals = ds.status === "fulfilled" ? ds.value : [];
    setKbId((cur) => cur || loadedBases[0]?.id || "");
    setScoreDealId((cur) => cur || loadedDeals[0]?.id || "");
  }

  useEffect(() => {
    reload().catch((e) => setNotice(String(e))).finally(() => setLoading(false));
  }, [agencyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const wrap = (fn: () => Promise<void>) => () =>
    fn().catch((e) => setNotice(e instanceof Error ? e.message : "falha"));
  const csv = (value: string) => value.split(",").map((x) => x.trim()).filter(Boolean);

  async function runLlm() {
    setLlmResult(await api.llmComplete({ user: llmPrompt }));
  }

  async function savePolicy() {
    await api.createGuardrailPolicy({
      name: policyName,
      rules: { blocked_phrases: csv(blocked), strict: false },
      active: true,
    });
    await reload();
  }

  async function evalGuardrail() {
    setGuardDecision(await api.evaluateGuardrail({ user_text: guardUser, assistant_text: guardAnswer, surface: "dashboard" }));
  }

  async function createKb() {
    const row = await api.createKnowledgeBase({ name: kbName, description: kbDescription });
    setKbId(row.id);
    await reload();
  }

  async function addDoc() {
    if (!kbId) return;
    const row = await api.addKnowledgeDocument(kbId, { title: docTitle, body: docBody });
    setNotice(`Documento indexado em ${row.chunks} chunk(s).`);
    await reload();
  }

  async function queryRag(answer = false) {
    if (!kbId) return;
    const result = await api.queryKnowledgeBase(kbId, { question: ragQuestion, k: 5, answer });
    setRagHits(result.hits);
    setRagAnswer(result.answer);
  }

  async function evalGovernance() {
    setGovDecision(await api.evaluateGovernance({
      action: govAction,
      regime: govRegime,
      confidence: govConfidence,
      impact: govImpact,
      reversible: govReversible,
    }));
  }

  async function runScore() {
    setScore(await api.scoreLead({
      deal_id: scoreDealId || undefined,
      title: scoreTitle,
      notes: scoreNotes,
      value_cents: scoreValue,
      apply: Boolean(scoreDealId),
    }));
    await reload();
  }

  async function saveNote() {
    await api.createVaultNote({
      kind: noteKind || undefined,
      title: noteTitle,
      body: noteBody,
      tags: csv(noteTags),
    });
    await reload();
  }

  async function searchVault() {
    setVaultHits((await api.searchVault(vaultQuery)).hits);
  }

  if (loading) return <div className="loading">Carregando inteligência…</div>;

  return (
    <div className="reveal">
      <div className="crumb">Intelligence · LLM + guardrails + RAG + scoring</div>
      <h1 className="h1">Dash de Inteligência</h1>
      {notice && <div className="notice">{notice}</div>}

      <div className="kpis" style={{ marginBottom: 18 }}>
        {tools.map((tool) => (
          <div className="kpi" key={tool.id}>
            <div className="v">{tool.count ?? "on"}</div>
            <div className="l">{tool.name}</div>
          </div>
        ))}
      </div>

      <div className="tabs">
        {TABS.map(([id, label]) => (
          <button key={id} className={"tab" + (tab === id ? " on" : "")} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {tab === "llm" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">Teste de provider</div>
            <textarea className="field" value={llmPrompt} onChange={(e) => setLlmPrompt(e.target.value)} />
            <button className="btn-primary" onClick={wrap(runLlm)}>Executar LLM</button>
          </div>
          <ResultPanel title="Resposta">
            {llmResult ? (
              <>
                <div className="row-actions">
                  <span className={"pill " + (llmResult.dry_run ? "amber" : "green")}>{llmResult.dry_run ? "dry-run" : "live"}</span>
                  <span className="pill cyan">{llmResult.provider}</span>
                  <span className="pill">{llmResult.model}</span>
                </div>
                <p className="muted" style={{ whiteSpace: "pre-wrap" }}>{llmResult.text}</p>
              </>
            ) : <div className="empty">Nenhuma chamada ainda.</div>}
          </ResultPanel>
        </div>
      )}

      {tab === "guardrails" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">Política</div>
            <input className="field" value={policyName} onChange={(e) => setPolicyName(e.target.value)} />
            <span className="field-label">termos bloqueados</span>
            <input className="field" value={blocked} onChange={(e) => setBlocked(e.target.value)} />
            <button className="btn-ghost" onClick={wrap(savePolicy)}>Salvar política</button>
            <div className="ptitle" style={{ marginTop: 12 }}>Avaliar</div>
            <textarea className="field" value={guardUser} onChange={(e) => setGuardUser(e.target.value)} />
            <textarea className="field" value={guardAnswer} onChange={(e) => setGuardAnswer(e.target.value)} />
            <button className="btn-primary" onClick={wrap(evalGuardrail)}>Rodar guardrail</button>
          </div>
          <ResultPanel title="Resultado">
            {policies.map((p) => <div className="chip" key={p.id}>{p.name}</div>)}
            {guardDecision && (
              <div className="sess static">
                <div className="top">
                  <span className="nm">Ação: {guardDecision.action}</span>
                  <span className={"pill " + pillFor(guardDecision.action)}>risco {guardDecision.risk_score}</span>
                </div>
                {guardDecision.findings.map((f) => (
                  <div className="muted" key={f.code}>{f.severity}: {f.message}</div>
                ))}
              </div>
            )}
          </ResultPanel>
        </div>
      )}

      {tab === "rag" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">Base de conhecimento</div>
            <input className="field" value={kbName} onChange={(e) => setKbName(e.target.value)} />
            <input className="field" value={kbDescription} onChange={(e) => setKbDescription(e.target.value)} />
            <button className="btn-ghost" onClick={wrap(createKb)}>Criar base</button>
            <select className="field" value={kbId} onChange={(e) => setKbId(e.target.value)}>
              <option value="">Selecione uma base…</option>
              {bases.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <input className="field" value={docTitle} onChange={(e) => setDocTitle(e.target.value)} />
            <textarea className="field" value={docBody} onChange={(e) => setDocBody(e.target.value)} />
            <button className="btn-ghost" onClick={wrap(addDoc)} disabled={!kbId}>Indexar documento</button>
            <input className="field" value={ragQuestion} onChange={(e) => setRagQuestion(e.target.value)} />
            <div className="row-actions">
              <button className="btn-primary" onClick={wrap(() => queryRag(false))} disabled={!kbId}>Buscar</button>
              <button className="btn-ghost" onClick={wrap(() => queryRag(true))} disabled={!kbId}>Buscar + responder</button>
            </div>
          </div>
          <ResultPanel title="Bases e hits">
            {bases.map((b) => (
              <div className="sess static" key={b.id}>
                <div className="top">
                  <span className="nm">{b.name}</span>
                  <span className="pill cyan">{b.chunks} chunks</span>
                </div>
                <div className="muted">{b.description}</div>
              </div>
            ))}
            {ragAnswer && <div className="notice">{ragAnswer}</div>}
            {ragHits.map((h) => <Hit key={h.id} hit={h} />)}
          </ResultPanel>
        </div>
      )}

      {tab === "governance" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">Gate de governança</div>
            <input className="field" value={govAction} onChange={(e) => setGovAction(e.target.value)} />
            <div className="row-actions">
              <select className="field" value={govRegime} onChange={(e) => setGovRegime(e.target.value)}>
                <option value="manual">manual</option>
                <option value="semi">semi</option>
                <option value="auto">auto</option>
              </select>
              <select className="field" value={govImpact} onChange={(e) => setGovImpact(e.target.value)}>
                <option value="low">baixo</option>
                <option value="medium">médio</option>
                <option value="high">alto</option>
                <option value="critical">crítico</option>
              </select>
            </div>
            <span className="field-label">confiança: {govConfidence.toFixed(2)}</span>
            <input type="range" min="0" max="1" step="0.01" value={govConfidence} onChange={(e) => setGovConfidence(Number(e.target.value))} />
            <label className="chip">
              <input type="checkbox" checked={govReversible} onChange={(e) => setGovReversible(e.target.checked)} />
              reversível
            </label>
            <button className="btn-primary" onClick={wrap(evalGovernance)}>Avaliar ação</button>
          </div>
          <ResultPanel title="Decisão">
            {govDecision ? (
              <div className="sess static">
                <div className="top">
                  <span className="nm">{govDecision.status}</span>
                  <span className={"pill " + pillFor(govDecision.status)}>risco {govDecision.risk_score}</span>
                </div>
                <p className="muted">{govDecision.reason}</p>
                <p className="muted">{govDecision.regime_description}</p>
              </div>
            ) : <div className="empty">Nenhuma decisão ainda.</div>}
          </ResultPanel>
        </div>
      )}

      {tab === "scoring" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">BANT / Lead score</div>
            <select className="field" value={scoreDealId} onChange={(e) => setScoreDealId(e.target.value)}>
              <option value="">sem deal vinculado</option>
              {deals.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
            <input className="field" value={scoreTitle} onChange={(e) => setScoreTitle(e.target.value)} />
            <textarea className="field" value={scoreNotes} onChange={(e) => setScoreNotes(e.target.value)} />
            <input className="field" type="number" value={scoreValue} onChange={(e) => setScoreValue(Number(e.target.value))} />
            <button className="btn-primary" onClick={wrap(runScore)}>Calcular score</button>
          </div>
          <ResultPanel title="Prioridade comercial">
            {score && (
              <div className="sess static">
                <div className="top">
                  <span className="nm">BANT {score.bant_score}/4 · {score.probability}%</span>
                  <span className={"pill " + pillFor(score.temperature)}>{score.temperature}</span>
                </div>
                <p className="muted">{score.next_best_action}</p>
                {score.explanation.map((x) => <span className="chip" key={x}>{x}</span>)}
              </div>
            )}
            {deals.slice(0, 8).map((d) => (
              <div className="row-item" key={d.id}>
                <div className="grow">
                  <div className="t">{d.title}</div>
                  <div className="muted">BANT {d.bant_score ?? 0}/4 · {d.next_best_action ?? "sem próxima ação"}</div>
                </div>
                <span className={"pill " + pillFor(d.temperature || "frio")}>{d.temperature || "frio"}</span>
              </div>
            ))}
          </ResultPanel>
        </div>
      )}

      {tab === "vault" && (
        <div className="split">
          <div className="panel formstack">
            <div className="ptitle">Nota operacional</div>
            <select className="field" value={noteKind} onChange={(e) => setNoteKind(e.target.value)}>
              <option value="methodology">metodologia</option>
              <option value="pitfall">pitfall</option>
              <option value="decision">decisão</option>
              <option value="note">nota</option>
            </select>
            <input className="field" value={noteTitle} onChange={(e) => setNoteTitle(e.target.value)} />
            <textarea className="field" value={noteBody} onChange={(e) => setNoteBody(e.target.value)} />
            <input className="field" value={noteTags} onChange={(e) => setNoteTags(e.target.value)} />
            <button className="btn-ghost" onClick={wrap(saveNote)}>Salvar no vault</button>
            <input className="field" value={vaultQuery} onChange={(e) => setVaultQuery(e.target.value)} />
            <button className="btn-primary" onClick={wrap(searchVault)}>Buscar no vault</button>
          </div>
          <ResultPanel title="Memória da operação">
            {vaultHits.map((h) => <Hit key={h.id} hit={h} />)}
            {notes.slice(0, 8).map((n) => (
              <div className="sess static" key={n.id}>
                <div className="top">
                  <span className="nm">{n.title}</span>
                  <span className="pill cyan">{n.kind}</span>
                </div>
                <div className="muted">{n.body}</div>
              </div>
            ))}
          </ResultPanel>
        </div>
      )}
    </div>
  );
}

function ResultPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="panel formstack">
      <div className="ptitle">{title}</div>
      {children}
    </div>
  );
}

function Hit({ hit }: { hit: RagHit }) {
  return (
    <div className="sess static">
      <div className="top">
        <span className="nm">{hit.title}</span>
        <span className="pill cyan">{hit.score.toFixed(3)}</span>
      </div>
      <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{hit.body.slice(0, 420)}</div>
    </div>
  );
}
