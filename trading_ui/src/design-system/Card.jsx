import './Card.css';

export function Card({ children, className = '', title, action, refreshing = false }) {
  return (
    <div className={`card ${refreshing ? 'card--refreshing' : ''} ${className}`}>
      {(title || action) && (
        <div className="card__header">
          <h3 className="card__title">{title}</h3>
          <div className="card__header-right">
            {refreshing && <span className="card__refresh-ring" aria-label="Refreshing" />}
            {action && <div className="card__action">{action}</div>}
          </div>
        </div>
      )}
      <div className="card__body">{children}</div>
    </div>
  );
}
