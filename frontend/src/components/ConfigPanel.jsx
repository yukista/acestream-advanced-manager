import { useEffect, useState } from 'react'

const FIELD_META = [
  {
    key: 'checks_enabled',
    label: 'Comprovacions activades',
    type: 'bool',
    help: 'Activa o atura el bucle automàtic de comprovacions.',
  },
  {
    key: 'checker_instances',
    label: 'Instàncies de comprovador',
    type: 'int',
    help: 'Nombre d\'instàncies de comprovador usades en paral·lel dins de cada cicle.',
  },
  {
    key: 'health_check_interval',
    label: 'Interval entre cicles (s)',
    type: 'int',
    help: 'Temps d\'espera quan acaba un cicle complet de canals.',
  },
  {
    key: 'health_probe_timeout_seconds',
    label: 'Timeout per comprovació (s)',
    type: 'int',
    help: 'Temps màxim per canal en cada prova via comprovador.',
  },
  {
    key: 'health_channel_gap_seconds',
    label: 'Pausa entre canals (s)',
    type: 'int',
    help: 'Separació entre comprovacions consecutives de canals.',
  },
  {
    key: 'max_segments',
    label: 'Màxim segments HLS',
    type: 'int',
    help: 'Nombre de fragments HLS que es mantenen al ring buffer.',
  },
  {
    key: 'hls_segment_time',
    label: 'Durada segment HLS (s)',
    type: 'int',
    help: 'Durada objectiu de cada fragment TS del stream.',
  },
]

export default function ConfigPanel({ settings, onSave, onReset, onRefresh }) {
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!settings?.values) return
    setDraft(settings.values)
  }, [settings])

  if (!settings || !draft) {
    return (
      <div className="empty-state">
        <span className="icon">⚙️</span>
        <span>Carregant configuració…</span>
      </div>
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(draft)
      await onRefresh()
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    setSaving(true)
    try {
      const ok = await onReset()
      if (ok) {
        await onRefresh()
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="config-wrap">
      <div className="section-title">Configuració del sistema</div>

      <div className="config-table">
        {FIELD_META.map((f) => {
          const schema = settings.schema?.[f.key] || {}
          const value = draft[f.key]
          return (
            <div className="config-row" key={f.key}>
              <div className="config-labels">
                <span className="config-label">{f.label}</span>
                <span className="config-help">{f.help}</span>
                {f.type === 'int' && (
                  <span className="config-range">Min {schema.min ?? '-'} · Max {schema.max ?? '-'}</span>
                )}
              </div>

              <div className="config-input-wrap">
                {f.type === 'bool' ? (
                  <label className="manager-switch">
                    <input
                      type="checkbox"
                      checked={!!value}
                      onChange={(e) => setDraft((prev) => ({ ...prev, [f.key]: e.target.checked }))}
                    />
                    <span>{value ? 'Sí' : 'No'}</span>
                  </label>
                ) : (
                  <input
                    className="manager-title"
                    type="number"
                    value={value ?? ''}
                    min={schema.min}
                    max={schema.max}
                    onChange={(e) => {
                      const raw = e.target.value
                      const n = raw === '' ? '' : Number(raw)
                      setDraft((prev) => ({ ...prev, [f.key]: n }))
                    }}
                  />
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="config-actions">
        <button className="btn-check" onClick={onRefresh} disabled={saving}>Refresca</button>
        <button className="btn-check" onClick={handleReset} disabled={saving}>Per defecte</button>
        <button className="btn-watch" onClick={handleSave} disabled={saving}>
          {saving ? 'Desant…' : 'Desa configuració'}
        </button>
      </div>
    </div>
  )
}
