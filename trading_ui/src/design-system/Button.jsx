import './Button.css';

export function Button({ children, variant = 'primary', size = 'md', onClick, disabled, className = '' }) {
  return (
    <button 
      className={`btn btn--${variant} btn--${size} ${className}`} 
      onClick={onClick} 
      disabled={disabled}
    >
      {children}
    </button>
  );
}
