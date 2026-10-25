function value = interp2_clamped(table, t_grid, soc_grid, temp, soc)
  % Bilinear lookup of table(j, m) at (temp, soc) with clamping (docs/model.md Eq. 4), as
  % python/ekfsoc/model.py interp2, in the same operation order. Named so as not to shadow interp2.
  [j, weight_t] = find_cell(t_grid, temp);
  [m, weight_s] = find_cell(soc_grid, soc);

  value_j = (1 - weight_s) * table(j, m) + weight_s * table(j, m + 1);
  value_j1 = (1 - weight_s) * table(j + 1, m) + weight_s * table(j + 1, m + 1);
  value = (1 - weight_t) * value_j + weight_t * value_j1;
end
