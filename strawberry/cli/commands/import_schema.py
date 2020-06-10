import sys
import re
import os
from os.path import abspath

import click

from graphql.language import parse
from graphql.error import GraphQLError

from ...utils.sdl_transpiler import render_template
from ...utils.str_converters import to_snake_case


# Regex pattern to extract import statement
GQL_IMPORT_REGEX = r"#import \"(.*\.gql|.*\.graphql)\""
GQL_SCHEMA_TYPE = r"(?si)^Schema.*?}"


def set_chdir(fn):
    """ Helps resolve relative imports based on paths passed as arguments """

    def wrapper(*args):
        path, imported = args
        previous_chdir = os.getcwd()
        os.chdir(os.path.dirname(path))
        paths = fn(path, imported)
        os.chdir(previous_chdir)
        return paths

    return wrapper


@click.command("import-schema", short_help="Parses SDL file to python dataclasses")
@click.argument("schema", type=str, required=True)
@click.option("-O", "--output", default="", type=str)
@click.option("-R", "--recursive", default=True, type=bool)
@click.option("-M", "--multifile", default=False, type=bool)
def import_schema(schema, output, recursive, multifile):
    """ Parses SDL file to python dataclasses and writes them out """
    try:
        # Find paths and eliminate duplicates
        paths = tuple(set(get_paths(schema, recursive)))
        ast = get_ast(paths)
        templates = []
        for definition in ast.definitions:
            templates.append(render_template(definition))

        if not multifile:
            imports = "import strawberry"
            schema_string = "\n\n".join(templates)
            imports += "\nimport typing\n\n" if "typing" in schema_string else ""
            schema_string = imports + schema_string
            write_strawberry_schema(schema_string, output, schema)

    except FileNotFoundError as e:
        print(f"File or files not found on schema path: {schema}")

    except GraphQLError as e:
        # TODO: Test this to see if print output can be improved
        print(f"A file contains syntax errors")


def get_ast(paths):
    """ Parse the content of files to AST """
    gql_strings = []
    for path in paths:
        # TODO: Option to print multiple files or single file
        gql_strings += gql_file_to_string(path)
    # Join read file strings and parse them to ast
    concatenation = "\n".join(gql_strings)
    # Replace schema {} with empty string, it will be generated by the server
    concatenation = re.sub(GQL_SCHEMA_TYPE, "", concatenation)
    ast = parse(concatenation)
    return ast


def get_paths(schema, recursive):
    """ Locate import statements and return them """
    paths = [schema]
    if recursive:
        paths += get_imports(schema, [])

    return paths


@set_chdir
def get_imports(path: str, imported: [str]) -> [str]:
    """ Extract imprort statements and make them path-like """
    paths = [path]
    if path in imported:
        return paths
    with open(path, "r") as file:
        schema_string = file.read()
        imports = re.findall(GQL_IMPORT_REGEX, schema_string)
        abs_imports = [abspath(imp) for imp in imports if abspath(imp) not in imported]
        for imp in abs_imports:
            paths += get_imports(imp, paths)

    return paths


def gql_file_to_string(path: str) -> [str]:
    """ Returns schema string """
    with open(path, "r") as file:
        string = file.read()
        string = re.sub(GQL_IMPORT_REGEX, "", string)
        string = re.sub(r"\n\n", "", string)

    return [string]


def write_strawberry_schema(schema_string, output, schema):
    file = os.path.split(schema)[1]
    filepath = os.path.join(output, to_snake_case(os.path.splitext(file)[0]) + ".py")
    with open(abspath(filepath), "w") as f:
        f.write(schema_string)
