function params = read_params(path)
  % Read results/s1/params.csv into the two axes and the seven tables, as python/ekfsoc/model.py
  % Params.from_csv. The file has one row per (T, soc), T-major; table row j is temperature t_grid(j)
  % and column m is SoC soc_grid(m).
  columns = {'T_degC', 'soc', 'ocv_V', 'docv_V_per_soc', 'R0_ohm', 'R1_ohm', 'tau1_s', 'R2_ohm', 'tau2_s'};
  tables = {'ocv', 'docv', 'r0', 'r1', 'tau1', 'r2', 'tau2'};

  if ~isequal(read_header(path), columns)
    error('%s: the header is not %s', path, strjoin(columns, ','));
  end
  data = dlmread(path, ',', 1, 0);

  n_soc = sum(data(:, 1) == data(1, 1));
  n_t = rows(data) / n_soc;
  if n_t ~= fix(n_t)
    error('%s: %d rows is not a whole number of blocks of %d', path, rows(data), n_soc);
  end
  params.t_grid = data(1:n_soc:end, 1);
  params.soc_grid = data(1:n_soc, 2);
  if ~isequal(data(:, 1), kron(params.t_grid, ones(n_soc, 1))) || ~isequal(data(:, 2), repmat(params.soc_grid, n_t, 1))
    error('%s: the T and soc columns do not form the same grid in every block', path);
  end

  for c = 1:numel(tables)
    params.(tables{c}) = reshape(data(:, 2 + c), n_soc, n_t)';
  end
end
