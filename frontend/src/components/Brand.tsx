import { AuditOutlined } from "@ant-design/icons";

// Product mark used in every header.
export function Brand({ onClick }: { onClick?: () => void }) {
  const body = (
    <>
      <span className="brand-mark" aria-hidden>
        <AuditOutlined />
      </span>
      <span className="brand-name">Revizorro</span>
    </>
  );
  return onClick ? (
    <button type="button" className="brand" onClick={onClick} title="На главную">
      {body}
    </button>
  ) : (
    <span className="brand">{body}</span>
  );
}
