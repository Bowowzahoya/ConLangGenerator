from __future__ import annotations

import sys
from pathlib import Path

import typer

from conlang_generator.core.spec import GenerationSpec, SeedExample
from conlang_generator.generation.generator import generate_language
from conlang_generator.generation.prompt_classifier import classify_prompt
from conlang_generator.generation.seed_examples import resolve_seed_examples
from conlang_generator.generation.sound_change import evolve_language
from conlang_generator.llm.factory import build_llm_client
from conlang_generator.speech import reader
from conlang_generator.storage.yaml_backend import YamlLanguageRepository
from conlang_generator.translation.translator import translate_to_conlang, translate_to_english

app = typer.Typer(help="Generate constructed languages and translate to/from English.")

LANGUAGES_DIR = Path("conlangs")
CACHE_DIR = Path(".cache")


def _repository() -> YamlLanguageRepository:
    return YamlLanguageRepository(LANGUAGES_DIR)


def _client(llm: str):
    try:
        return build_llm_client(kind=llm, cache_dir=CACHE_DIR)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _parse_seed_example(raw: str) -> SeedExample:
    if "=" not in raw:
        typer.echo(f"error: --example must be 'gloss=form' or 'gloss=form|ipa', got {raw!r}", err=True)
        raise typer.Exit(code=1)
    gloss, rest = raw.split("=", 1)
    form, _, ipa = rest.partition("|")
    return SeedExample(gloss=gloss.strip(), form=form.strip(), ipa=(ipa.strip() or None))


@app.command()
def generate(
    prompt: str = typer.Option(..., "--prompt", help="Free-text description of the language."),
    name: str = typer.Option(..., "--name", help="Name to save the language under."),
    seed: int = typer.Option(0, "--seed", help="Random seed for reproducibility."),
    llm: str = typer.Option("fake", "--llm", help="LLM backend: fake or anthropic."),
    isolated: bool = typer.Option(False, "--isolated", help="Force isolated-community typology (guaranteed, not just likely)."),
    high_altitude: bool = typer.Option(False, "--high-altitude", help="Force ejective consonants (guaranteed, not just likely)."),
    tonal: bool = typer.Option(False, "--tonal", help="Force phonemic tone (guaranteed, not just likely)."),
    fantasy: bool = typer.Option(False, "--fantasy", help="Record as a fantasy-setting language (metadata only)."),
    contact_language: list[str] = typer.Option(
        [], "--contact-language", help="Bias generation toward a known real language's palette (repeatable); merged with any the prompt implies."
    ),
    example: list[str] = typer.Option(
        [], "--example", help="Literal seed word: 'gloss=form' or 'gloss=form|ipa' (repeatable). Always appears verbatim in the lexicon."
    ),
    evolve_from: str = typer.Option(
        None, "--evolve-from", help="Evolve an existing saved language via sound change instead of generating fresh (requires --years)."
    ),
    years: int = typer.Option(None, "--years", help="Time depth in years, for --evolve-from."),
) -> None:
    """Generate a new language and save it."""
    client = _client(llm)
    traits = classify_prompt(prompt, fantasy, client)
    if contact_language:
        merged = tuple(dict.fromkeys((*traits.contact_languages, *contact_language)))
        traits = traits.model_copy(update={"contact_languages": merged})

    if evolve_from is not None:
        if years is None:
            typer.echo("error: --evolve-from requires --years", err=True)
            raise typer.Exit(code=1)
        repository = _repository()
        try:
            base = repository.load(evolve_from)
        except FileNotFoundError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        language = evolve_language(name, base, years, traits, seed)
        repository.save(language)

        typer.echo(f"Evolved '{evolve_from}' -> '{language.name}' ({language.slug}) over {years} years.")
        typer.echo(
            f"consonants: {len(base.phonology.consonants)} -> {len(language.phonology.consonants)}, "
            f"vowels: {len(base.phonology.vowels)} -> {len(language.phonology.vowels)}"
        )
        nonzero_traits = {k: v for k, v in traits.model_dump().items() if isinstance(v, float) and v != 0.0}
        if nonzero_traits:
            typer.echo(f"Evolution traits: {', '.join(f'{k}={v:+.2f}' for k, v in nonzero_traits.items())}")
        for old_entry, new_entry in list(zip(base.lexicon.entries, language.lexicon.entries))[:6]:
            arrow = "=" if old_entry.romanization == new_entry.romanization else "->"
            typer.echo(f"  {old_entry.glosses[0]}: {old_entry.romanization} {arrow} {new_entry.romanization}")
        typer.echo(f"Saved to {LANGUAGES_DIR / language.slug}")
        return

    raw_examples = tuple(_parse_seed_example(e) for e in example)
    seed_examples = resolve_seed_examples(raw_examples, client)

    spec = GenerationSpec(
        prompt=prompt,
        seed=seed,
        traits=traits,
        force_isolated=isolated,
        force_high_altitude=high_altitude,
        force_tonal=tonal,
        fantasy=fantasy,
        seed_examples=seed_examples,
    )
    language = generate_language(name, spec, client)
    _repository().save(language)

    typer.echo(f"Generated '{language.name}' ({language.slug}) -- {len(language.lexicon.entries)} core words.")
    typer.echo(
        f"Word order: {language.grammar.word_order.value}, "
        f"morphology: {language.grammar.morphological_type.value}, "
        f"alignment: {language.grammar.alignment.value}, "
        f"tonal: {language.tone_system.enabled}"
    )

    nonzero_traits = {
        trait_name: value
        for trait_name, value in traits.model_dump().items()
        if isinstance(value, float) and value != 0.0
    }
    if nonzero_traits:
        rendered = ", ".join(f"{k}={v:+.2f}" for k, v in nonzero_traits.items())
        typer.echo(f"Traits from prompt: {rendered}")
    if traits.contact_languages:
        typer.echo(f"Contact languages: {', '.join(traits.contact_languages)}")
    forced = [f for f, on in (("isolated", isolated), ("high_altitude", high_altitude), ("tonal", tonal)) if on]
    if forced:
        typer.echo(f"Forced (guaranteed): {', '.join(forced)}")
    if seed_examples:
        rendered_examples = ", ".join(f"{e.gloss}={e.form} (/{e.ipa}/)" for e in seed_examples)
        typer.echo(f"Seed examples: {rendered_examples}")

    typer.echo(f"Saved to {LANGUAGES_DIR / language.slug}")


@app.command()
def translate(
    text: str = typer.Argument(..., help="Text to translate."),
    lang: str = typer.Option(..., "--lang", help="Language name."),
    to: str = typer.Option("conlang", "--to", help="Direction: 'conlang' or 'english'."),
    llm: str = typer.Option("fake", "--llm", help="LLM backend: fake or anthropic."),
) -> None:
    """Translate text to or from a generated language."""
    if to not in ("conlang", "english"):
        typer.echo("error: --to must be 'conlang' or 'english'", err=True)
        raise typer.Exit(code=1)

    repository = _repository()
    try:
        language = repository.load(lang)
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    client = _client(llm)

    if to == "conlang":
        result = translate_to_conlang(text, language, client)
        typer.echo(result.text)
        typer.echo(f"IPA: /{result.ipa}/")
    else:
        result = translate_to_english(text, language, client)
        typer.echo(result.text)

    if result.coined:
        repository.save(result.language)
        coined_forms = ", ".join(e.romanization for e in result.coined)
        typer.echo(f"Coined {len(result.coined)} new word(s): {coined_forms}")
    typer.echo(f"(pattern: {result.pattern})")


@app.command()
def pronounce(
    word: str = typer.Argument(..., help="An English gloss or a conlang word (romanized or IPA form)."),
    lang: str = typer.Option(..., "--lang", help="Language name."),
) -> None:
    """Show IPA and romanization for a known word. No audio synthesis yet."""
    try:
        language = _repository().load(lang)
    except FileNotFoundError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    entry = reader.lookup_pronunciation(language, word)
    if entry is None:
        typer.echo(f"'{word}' is not in {lang}'s lexicon yet.")
        raise typer.Exit(code=1)
    typer.echo(reader.describe(entry))


def main() -> None:
    # IPA and tone diacritics are outside cp1252 -- Windows terminals default
    # to it, so force UTF-8 output rather than crashing on the first accent.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    app()


if __name__ == "__main__":
    main()
