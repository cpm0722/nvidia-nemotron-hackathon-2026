"""output_parser.parse_product_names 단위 테스트."""

import pytest

from nat_query_generator.models import QueryGeneratorOutput
from nat_query_generator.output_parser import parse_product_names


def test_single_product():
    result = parse_product_names('["Gemma4"]')
    assert result == QueryGeneratorOutput(product_names=["Gemma4"])


def test_multiple_products():
    result = parse_product_names('["GPT 5", "GPT 5.1"]')
    assert result == QueryGeneratorOutput(product_names=["GPT 5", "GPT 5.1"])


def test_markdown_json_code_block():
    result = parse_product_names('```json\n["Claude Design"]\n```')
    assert result == QueryGeneratorOutput(product_names=["Claude Design"])


def test_markdown_code_block_no_lang():
    result = parse_product_names('```\n["codex"]\n```')
    assert result == QueryGeneratorOutput(product_names=["codex"])


def test_empty_array():
    result = parse_product_names("[]")
    assert result == QueryGeneratorOutput(product_names=[])


def test_invalid_json_raises():
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_product_names("not a json")


def test_json_object_raises():
    with pytest.raises(ValueError, match="Expected JSON array"):
        parse_product_names('{"product": "GPT-5"}')


def test_array_with_non_strings_raises():
    with pytest.raises(ValueError, match="Expected array of strings"):
        parse_product_names("[1, 2, 3]")


def test_leading_trailing_whitespace():
    result = parse_product_names('  ["Sonnet 4.6"]  ')
    assert result == QueryGeneratorOutput(product_names=["Sonnet 4.6"])


def test_markdown_block_with_whitespace():
    result = parse_product_names('```json\n  ["Nemotron"]  \n```')
    assert result == QueryGeneratorOutput(product_names=["Nemotron"])
