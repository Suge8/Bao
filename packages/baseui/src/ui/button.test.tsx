import { render, screen } from "@testing-library/react";
import { Button } from "./button";

test("Button renders label", () => {
  render(<Button>OK</Button>);
  expect(screen.getByRole("button", { name: "OK" })).toBeTruthy();
});
