from genshin_sim.cli.main import main


def test_main_prints_project_name(capsys):
    main()

    captured = capsys.readouterr()
    assert captured.out == "Genshin Simulation Lab\n"
