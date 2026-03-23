export default function SearchBar({ value, onChange, onSubmit }) {
  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-2 sm:flex-row">
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="input"
        placeholder="Search by symbol or company name"
      />
      <button type="submit" className="btn-primary sm:w-36">
        Search
      </button>
    </form>
  );
}
