function inputs = read_inputs(path)
  % The filter inputs of a CSV as c/tools/ekf_run_csv.c reads them: the columns dt_s, i_a, v_v and
  % t_degc, found by header name in any order, other columns ignored. Returns an n x 4 matrix in that
  % column order. A missing column, a missing value or a non-finite value is an error.
  names = {'dt_s', 'i_a', 'v_v', 't_degc'};
  [found, columns] = ismember(names, read_header(path));
  if ~all(found)
    error('%s: cannot read the columns dt_s, i_a, v_v, t_degc', path);
  end
  values = dlmread(path, ',', 1, 0, 'emptyvalue', NaN);
  inputs = values(:, columns);
  if ~all(isfinite(inputs(:)))
    error('%s: a filter input is missing or not finite', path);
  end
end
