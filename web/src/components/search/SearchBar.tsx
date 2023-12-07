import React, { KeyboardEvent, ChangeEvent } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";

interface SearchBarProps {
  query: string;
  setQuery: (query: string) => void;
  onSearch: () => void;
}

export const SearchBar = ({ query, setQuery, onSearch }: SearchBarProps) => {
  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const target = event.target;
    setQuery(target.value);

    // Resize the textarea to fit the content
    target.style.height = "24px";
    const newHeight = target.scrollHeight;
    target.style.height = `${newHeight}px`;
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      onSearch();
      event.preventDefault();
    }
  };

  return (
    <div className="flex justify-center">
      <div className="flex items-center w-full border-2 border-logo-lightblue-400 rounded-2xl px-4 py-2 focus-within:border-logo-lightblue-600">
        <MagnifyingGlass className="text-[#000099]" />
        <textarea
          autoFocus
          className="flex-grow ml-2 h-6 bg-transparent outline-none placeholder-gray-400 overflow-hidden whitespace-normal resize-none text-logo-darkblue-600"
          role="textarea"
          aria-multiline
          placeholder="Message PayserAi..."
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          suppressContentEditableWarning={true}
        />
      </div>
    </div>
  );
};
