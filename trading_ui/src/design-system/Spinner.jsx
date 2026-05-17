import './Spinner.css';

export function Spinner({ size = 'md' }) {
  return <div className={`spinner spinner--${size}`} />;
}
