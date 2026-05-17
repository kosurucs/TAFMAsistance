import './Card.css';

export function Card({ children, className = '', title, action }) {
  return (
    <div className={`card ${className}`}>
      {(title || action) && (
        <div className="card__header">
          <h3 className="card__title">{title}</h3>
          {action && <div className="card__action">{action}</div>}
        </div>
      )}
      <div className="card__body">{children}</div>
    </div>
  );
}
