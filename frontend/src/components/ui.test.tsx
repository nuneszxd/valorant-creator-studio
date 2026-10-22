import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TimeInput } from "./TimeInput";
import { NumberInput } from "./ui";

describe("NumberInput", () => {
  it("lets you type a negative number and only reports valid values while typing", () => {
    const onChange = vi.fn();
    render(<NumberInput value={0} onChange={onChange} min={-30} max={20} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "-" } });
    expect(input.value).toBe("-");
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "-3" } });
    expect(onChange).toHaveBeenLastCalledWith(-3);
    expect(input.value).toBe("-3");
  });

  it("does not snap an emptied field back to a default while you are still editing", () => {
    const onChange = vi.fn();
    render(<NumberInput value={20} onChange={onChange} min={12} max={35} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "" } });
    expect(input.value).toBe("");
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.blur(input); // leaving an empty field reports null so the caller can apply its default
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("clamps to min/max when the field loses focus", () => {
    const onChange = vi.fn();
    render(<NumberInput value={10} onChange={onChange} min={0} max={20} />);
    const input = screen.getByRole("textbox") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "99" } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith(20);
    expect(input.value).toBe("20");
  });
});

describe("TimeInput", () => {
  it("only reports a change when the position really moves", () => {
    const onChange = vi.fn();
    render(<TimeInput value={65.5} onChange={onChange} ariaLabel="Início" />);
    const input = screen.getByLabelText("Início") as HTMLInputElement;
    expect(input.value).toBe("1:05.5");
    fireEvent.blur(input); // same value: must not mark the form as edited
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "2:00" } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenLastCalledWith(120);
  });

  it("restores the previous value when the text is invalid", () => {
    const onChange = vi.fn();
    render(<TimeInput value={30} onChange={onChange} ariaLabel="Fim" />);
    const input = screen.getByLabelText("Fim") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.blur(input);
    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe("0:30.0");
  });
});
