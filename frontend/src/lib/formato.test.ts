import { describe, expect, it } from "vitest";
import { fData, fMoeda, fPct, segundaDe, somarDias } from "./formato";

describe("formatação PT", () => {
  it("datas em DD/MM/AAAA", () => {
    expect(fData("2026-03-05")).toBe("05/03/2026");
    expect(fData(null)).toBe("—");
  });
  it("Kwanza", () => {
    expect(fMoeda(1234567.5)).toBe("1.234.567,50 Kz");
    expect(fMoeda("9000")).toBe("9.000,00 Kz");
    expect(fMoeda(-250)).toBe("-250,00 Kz");
    expect(fPct(54.5)).toBe("54,5%");
    expect(fPct("100.0")).toBe("100%");
    expect(fPct(null)).toBe("—");
  });
  it("aritmética de datas sem fuso", () => {
    expect(somarDias("2026-02-28", 1)).toBe("2026-03-01");
    expect(segundaDe("2026-11-22")).toBe("2026-11-16");
    expect(segundaDe("2026-11-16")).toBe("2026-11-16");
  });
});

import { fQtd } from "./formato";
describe("quantidades", () => {
  it("formata em pt-PT com unidade", () => {
    expect(fQtd("1234.500", "ml")).toBe("1234,5 ml"); // pt-PT só agrupa a partir de 5 dígitos
    expect(fQtd("12345", "un").replace(/\s/g, " ")).toBe("12 345 un.");
    expect(fQtd(null)).toBe("—");
  });
});
