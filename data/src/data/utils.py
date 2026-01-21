
import PyPDF2
from pathlib import Path
import re


def mk_txt_from_pdf(filepath_pdf, filepath_txt):
    with open(filepath_pdf, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        number_of_pages = len(reader.pages)
        text = ""
        for page_number in range(number_of_pages):
            page = reader.pages[page_number]
            text += page.extract_text() + "\n\n"

    with open(filepath_txt, "w", encoding="utf-8") as text_file:
        text_file.write(text)





def rename_files_with_dates(rename = False,directory_path="fabricated",file_extension="txt"):
    for file in Path(directory_path).glob(f"*.{file_extension}"):
        #print(file.name)
        pattern_date = re.compile(r"\d{4}-\d{2}-\d{2}")
        pattern_year = re.compile(r"\d{4}")
        match_date = pattern_date.search(file.name)
        match_year = pattern_year.search(file.name)
        if match_date:
            new_filename = match_date.group(0) + "_" + file.name
            if rename:
                file.rename(file.parent / new_filename)
            else:
                print(new_filename)
        elif match_year:
            new_filename = match_year.group(0) + "_" + file.name
            if rename:
                file.rename(file.parent / new_filename)
            else:
                print(new_filename)
        else:
            pass
            print(f"----NO DATE FOUND: {file.name}----")