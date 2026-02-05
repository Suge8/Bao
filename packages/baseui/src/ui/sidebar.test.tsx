import { render, screen } from "@testing-library/react";
import { Sidebar } from "./sidebar";

test("Sidebar renders children", () => {
  render(
    <Sidebar compact={false}>
      <div>Nav</div>
    </Sidebar>,
  );
  expect(screen.getByText("Nav")).toBeTruthy();
});
