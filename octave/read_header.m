function names = read_header(path)
  % The column names of the first line of a CSV file, as a row cell array.
  fid = fopen(path, 'r');
  if fid < 0
    error('%s: cannot read', path);
  end
  line = fgetl(fid);
  fclose(fid);
  if ~ischar(line)
    error('%s: no header line', path);
  end
  names = strtrim(strsplit(line, ','));
end
