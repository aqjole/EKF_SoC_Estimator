function value = ekf_lookup(ekf, name, t_degc, soc)
  % Read table `name` at (t_degc, soc) with the clamped bilinear rule (Eq. 4), as Ekf.lookup.
  value = interp2_clamped(ekf.params.(name), ekf.params.t_grid, ekf.params.soc_grid, t_degc, soc);
end
